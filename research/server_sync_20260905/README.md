# CoPE / ReKep 服务器文件去重归档（2026-09-05）

本归档补充原 GitHub 提交 `7293f0a84521d81e58fc452b75a7cd0e7265ebe5` 未包含的服务器代码和实验结果。包含 CoPE、ReKep；按用户要求排除 HEART。服务器源文件未改动。

- 20,092 条来源文件记录：19,495 个普通文件路径、4 个 ZIP/TAR 中的 597 个普通文件成员。
- 新增 **4,265 份唯一文件内容，243,897,573 字节（243.90 MB）**。
- 4,618 条来源复用本次新增内容，11,209 条来源直接复用原 GitHub 文件。当前新增 payload 的 Git blob 全部互异，且均不在原 GitHub 文件集合中。
- 来源字节总数 534,325,860；内容去重避免重复存放 290,428,287 字节。数量按来源路径/归档成员统计，不代表独立科研成果数量。
- 原 GitHub 文件保持不变；本轮不清理旧仓库原有的重复路径。

## 内容与来源

`content/` 每种文件内容仅存放一份；相同内容的其他路径通过 [source_manifest.csv](source_manifest.csv) 关联。优先保留当前 R4 路径，然后是 R4 结果、fvl10 差异、R3、R2、ReKep、早期工作目录、归档独有成员。

主要来源为 fvl12 的 `/home/lijingsu/`（CoPE 各工作目录、代码包、结果与 ReKep）和 fvl10 的 `/mnt/data_new/lijingsu_cope_r4_20260905/`。R4 代码包含 202 个文件、本轮十个结果目录含 223 个；这些数字包含说明、配置与随包结果。

R2 源 ZIP 保留了 4 个与当前展开版本不同的代码文件，已单独纳入。其余归档成员复用已保留内容；不再上传整包。归档压缩字节与 Git 历史运输包不属于本次还原范围。

- [目录统计](summary.csv)
- [归档成员统计](archive_summary.csv)
- [排除范围](exclusions.csv)

文件映射记录服务器、原路径、归档成员、大小、权限、Git blob SHA-1、SHA256、存放位置。`reuse_existing` 指向原仓库路径；`new_canonical` 是本次单份内容；`reuse_new` 指向同批新增的单份内容。内容 SHA 和来源权限均单独保存。

## 还原完整目录

**这是去重归档，`content/` 不是可直接运行的完整项目。** 重复的代码、配置、空文件和结果只存一次，运行前应按清单还原。还原后的工作目录会包含项目需要的各个原始路径。

在包含本次归档的 Git 仓库版本根目录中运行下例。第一个参数为尚不存在的新目录；第二个参数为可选来源前缀。例子仅还原 fvl12 的 R4 包；省略第二个参数可还原全部来源。为保证结果固定，可先切换到引入本归档的提交再执行。

```bash
python3 - /path/to/new-restored-directory fvl12/v/cope_r4_20260905/ <<'PY'
import csv, hashlib, io, os, subprocess, sys
from pathlib import Path, PurePosixPath

repo = Path.cwd()
manifest_path = "research/server_sync_20260905/source_manifest.csv"
manifest = subprocess.check_output(["git", "show", "HEAD:" + manifest_path], cwd=repo).decode("utf-8")
selected_prefix = sys.argv[2] if len(sys.argv) > 2 else ""
rows = [r for r in csv.DictReader(io.StringIO(manifest)) if r["restore_path"].startswith(selected_prefix)]
if not rows:
    raise SystemExit("No source paths match the selected prefix")
destination = Path(sys.argv[1]).expanduser().resolve()
if destination.exists():
    raise SystemExit("Choose a new destination directory; existing paths will not be overwritten")
seen = set()
for r in rows:
    rel = PurePosixPath(r["restore_path"])
    if rel.is_absolute() or ".." in rel.parts or r["restore_path"] in seen:
        raise SystemExit("Unsafe or duplicate restore path")
    seen.add(r["restore_path"])
destination.mkdir(parents=True, exist_ok=False)
for r in rows:
    data = subprocess.check_output(["git", "cat-file", "blob", r["git_blob_sha1"]], cwd=repo)
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + bytes([0]) + data).hexdigest()
    if len(data) != int(r["size"]) or blob != r["git_blob_sha1"] or hashlib.sha256(data).hexdigest() != r["sha256"]:
        raise SystemExit("Content verification failed: " + r["source_path"])
    target = destination.joinpath(*PurePosixPath(r["restore_path"]).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as f:
        f.write(data)
    os.chmod(target, int(r["source_mode"], 8) & 0o777)
print("Restored and verified", len(rows), "files to", destination)
PY
```

脚本从 Git 对象读取内容，每个来源单独复制；逐文件验证大小、SHA-1、SHA256 并恢复原权限。不覆盖已有目的目录，不依赖服务器，也不建立硬链接。归档成员还原在 `archive_members/` 下，普通文件按 `fvl12/`、`fvl10/` 路径还原。

## 核验与范围

同步时重新计算全部入选来源的完整哈希，并对 SSH 接收的新内容再次验证哈希、大小和执行权限。新增内容经过凭据模式检查，未发现命中项。提交前核对所有来源映射、路径冲突、原树保留和全局内容去重；上传后再以 GitHub 实际提交树核对。

环境、权重、数据集、常见缓存、用户配置、凭据、第三方上游检出、Git 元数据、进程 ID、Mac 元数据和符号链接目标不在范围内。当前文件版本按内容保留；没有导入 15 个 bundle 中的完整 Git 历史。实验结果原样归档，不表示本次重新运行或确认其科学有效性。
