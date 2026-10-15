# -*- coding: utf-8 -*-
"""GitHub Actions 에서 실행: 승인되어 저장소에 올라온 게시물 중 발행일이 된 것을 게시.

저장소 구조: queue/<client>/<YYYY-MM-DD>/{01.jpg..., caption.txt, meta.json}
게시 후 published.json 을 남기고 jpg 는 지운다 (커밋은 워크플로 다음 단계에서).
계정 정보: 환경변수 IG_ACCOUNTS = {"<client>": {"token": "...", "user_id": "..."}}
"""
import datetime, json, os, pathlib, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

KST = datetime.timezone(datetime.timedelta(hours=9))
GRAPH = "https://graph.instagram.com"
ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = os.environ["GITHUB_REPOSITORY"]
RAW = f"https://raw.githubusercontent.com/{REPO}/main"


def call(method, path, token, params=None):
    params = dict(params or {}, access_token=token)
    url = f"{GRAPH}/{path}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method), timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')}") from None


def wait_public(url, tries=40):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as r:
                if r.status == 200:
                    return
        except urllib.error.HTTPError:
            pass
        time.sleep(3)
    raise RuntimeError(f"공개 URL 접근 실패: {url}")


def wait_finished(cid, token, tries=40):
    for _ in range(tries):
        code = call("GET", cid, token, {"fields": "status_code"}).get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {cid} status={code}")
        time.sleep(3)
    raise RuntimeError(f"container {cid} 처리 시간 초과")


def publish(post_dir, acct):
    token, user = acct["token"], acct["user_id"]
    rel = post_dir.relative_to(ROOT).as_posix()
    images = sorted(post_dir.glob("*.jpg"))
    caption = (post_dir / "caption.txt").read_text(encoding="utf-8").strip()
    children = []
    for img in images:
        url = f"{RAW}/{rel}/{img.name}"
        wait_public(url)
        children.append(call("POST", f"{user}/media", token, {"image_url": url, "is_carousel_item": "true"})["id"])
    for cid in children:
        wait_finished(cid, token)
    carousel = call("POST", f"{user}/media", token,
                    {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})["id"]
    wait_finished(carousel, token)
    media_id = call("POST", f"{user}/media_publish", token, {"creation_id": carousel})["id"]
    info = call("GET", media_id, token, {"fields": "permalink,timestamp"})
    (post_dir / "published.json").write_text(
        json.dumps({"media_id": media_id, **info}, ensure_ascii=False, indent=2), encoding="utf-8")
    for img in images:
        img.unlink()
    return info.get("permalink")


PUBLISH_AT = datetime.time(7, 30)   # 50·60대 활동 시간. 이 시각 전에는 절대 게시하지 않는다


def wait_until_publish_time():
    """예약 실행은 GitHub 사정으로 늦게 시작될 수 있어 일찍 신청해 두고, 07:30까지 기다린다."""
    now = datetime.datetime.now(KST)
    target = datetime.datetime.combine(now.date(), PUBLISH_AT, KST)
    if now < target:
        wait = (target - now).total_seconds()
        print(f"[wait] {target:%H:%M} 게시 시각까지 {wait / 60:.0f}분 대기", flush=True)
        time.sleep(wait)
        # 기다리는 동안 승인된 게시물이 있을 수 있으니 최신 상태로 갱신
        subprocess.run(["git", "pull", "--rebase", "--quiet"], cwd=ROOT, check=False)


def main():
    accounts = json.loads(os.environ["IG_ACCOUNTS"])
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        wait_until_publish_time()
    today = datetime.datetime.now(KST).date().isoformat()
    failed = False
    for meta_file in sorted(ROOT.glob("queue/*/*/meta.json")):
        post_dir = meta_file.parent
        client, date = post_dir.parent.name, post_dir.name
        if (post_dir / "published.json").exists():
            continue
        if date > today:
            print(f"[wait] {client}/{date} 발행일 전")
            continue
        if client not in accounts:
            print(f"[skip] {client}: IG_ACCOUNTS 에 계정 정보 없음")
            continue
        try:
            link = publish(post_dir, accounts[client])
            print(f"[published] {client}/{date} → {link}")
        except Exception as e:  # 한 건이 실패해도 나머지는 진행
            failed = True
            print(f"[ERROR] {client}/{date}: {e}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
