# -*- coding: utf-8 -*-
"""GitHub Actions 에서 주 1회 실행: 인스타그램 장기 토큰(60일)을 연장해 새 IG_ACCOUNTS 를 파일로 쓴다.
비밀값 갱신(gh secret set)은 워크플로 다음 단계에서 한다. 토큰은 출력하지 않는다.
"""
import json, os, sys, urllib.parse, urllib.request

accounts = json.loads(os.environ["IG_ACCOUNTS"])
for client, acct in accounts.items():
    url = "https://graph.instagram.com/refresh_access_token?" + urllib.parse.urlencode(
        {"grant_type": "ig_refresh_token", "access_token": acct["token"]})
    with urllib.request.urlopen(url, timeout=60) as r:
        res = json.loads(r.read().decode())
    acct["token"] = res["access_token"]
    print(f"[OK] {client}: 남은 기간 {int(res.get('expires_in', 0)) // 86400}일")

with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(accounts, f)
