# -*- coding: utf-8 -*-
import sys, os, json, subprocess
import urllib.request, urllib.error

REPO     = "frontier0553/bemi-universe"
EXE_NAME = "bemi-universe.exe"
BASE     = os.path.dirname(os.path.abspath(__file__))

def read_file(name):
    p = os.path.join(BASE, name)
    return open(p, encoding="utf-8").read().strip()

def write_file(name, content):
    p = os.path.join(BASE, name)
    open(p, "w", encoding="utf-8").write(content + "\n")

def bump_version(current, kind):
    parts = [int(x) for x in current.split(".")]
    while len(parts) < 3:
        parts.append(0)
    if kind == "1":      # 큰 변화
        parts = [parts[0] + 1, 0, 0]
    elif kind == "2":    # 작은 변화
        parts = [parts[0], parts[1] + 1, 0]
    else:                # 아주 작은 변화
        parts = [parts[0], parts[1], parts[2] + 1]
    return f"{parts[0]}.{parts[1]}.{parts[2]}"

def api_post(path, token, data):
    url = f"https://api.github.com/repos/{REPO}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def _upload(release_id, token, path, filename_encoded):
    url = f"https://uploads.github.com/repos/{REPO}/releases/{release_id}/assets?name={filename_encoded}"
    with open(path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"token {token}",
        "Content-Type": "application/octet-stream",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

def upload_asset(release_id, token, exe_path):
    return _upload(release_id, token, exe_path, "bemi-universe.exe")

def upload_asset_named(release_id, token, path, name):
    import urllib.parse
    return _upload(release_id, token, path, urllib.parse.quote(name))

def run(cmd, **kw):
    result = subprocess.run(cmd, shell=True, cwd=BASE, **kw)
    return result.returncode == 0

def main():
    interactive = "--interactive" in sys.argv

    # 버전/토큰
    if interactive:
        cur = read_file("version.txt")
        print(f"\n현재 버전: {cur}")
        print("  [1] 큰 변화     (+1.0.0)")
        print("  [2] 작은 변화   (+0.1.0)")
        print("  [3] 아주 작은   (+0.0.1)")
        kind = input("선택 (1/2/3): ").strip()
        if kind not in ("1", "2", "3"):
            print("[ERROR] 1, 2, 3 중 입력"); return
        new_ver = bump_version(cur, kind)
        print(f"새 버전: {new_ver}")
        token = read_file("github_token.txt")
    else:
        if len(sys.argv) < 3:
            print("사용법: python deploy.py <버전> <토큰>"); return
        new_ver = sys.argv[1].strip()
        token   = sys.argv[2].strip()

    print(f"\n[1/4] version.txt → {new_ver}")
    write_file("version.txt", new_ver)

    print("[2/4] EXE 빌드 중 (20~40분)...")
    run("python gen_icon.py", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not run("pyinstaller 배미유니버스_full.spec --clean --noconfirm"):
        print("[ERROR] 빌드 실패"); return

    print("  빌드 완료 — zip 압축 중...")
    import zipfile, pathlib
    dist_dir = os.path.join(BASE, "dist", "bemi-universe")
    ino_dir  = os.path.join(BASE, "ino")
    zip_path = os.path.join(BASE, "dist", "bemi-universe.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in pathlib.Path(dist_dir).rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(dist_dir))
        for f in pathlib.Path(ino_dir).rglob("*"):
            if f.is_file():
                zf.write(f, pathlib.Path("ino") / f.relative_to(ino_dir))
    print(f"  zip 완료: {os.path.getsize(zip_path) // 1024 // 1024}MB")

    print("[3/4] Git push...")
    run("git add version.txt")
    run(f'git commit -m "v{new_ver}"')
    if not run("git push"):
        print("[ERROR] push 실패"); return

    # 런처 항상 새로 빌드
    launcher_path = os.path.join(BASE, "dist", "배미유니버스_런처.exe")
    print("  런처 빌드 중...")
    subprocess.run("pyinstaller launcher.spec --clean --noconfirm",
                   shell=True, cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("[4/4] GitHub Release 생성 및 업로드...")
    try:
        release = api_post("/releases", token, {
            "tag_name": f"v{new_ver}", "name": f"v{new_ver}",
            "body": "", "draft": False, "prerelease": False
        })
        rid = release["id"]
        print(f"  Release ID: {rid}")

        # 메인 zip 업로드
        zip_path = os.path.join(BASE, "dist", "bemi-universe.zip")
        print(f"  zip 업로드 중 (시간 소요)...")
        r1 = _upload(rid, token, zip_path, "bemi-universe.zip")
        print(f"  메인 zip: {r1.get('state')}")

        # 런처 EXE 업로드 (최초 설치용)
        if os.path.exists(launcher_path):
            r2 = upload_asset_named(rid, token, launcher_path, "launcher.exe")
            print(f"  런처 EXE: {r2.get('state')}")


    except Exception as e:
        print(f"[ERROR] GitHub 오류: {e}"); return

    print(f"\n완료! https://github.com/{REPO}/releases/tag/v{new_ver}")
    print(f"처음 설치하는 사람에게 런처 링크 전달:")
    print(f"https://github.com/{REPO}/releases/latest/download/%EB%B0%B0%EB%AF%B8%EC%9C%A0%EB%8B%88%EB%B2%84%EC%8A%A4_%EB%9F%B0%EC%B2%98.exe")

if __name__ == "__main__":
    main()
