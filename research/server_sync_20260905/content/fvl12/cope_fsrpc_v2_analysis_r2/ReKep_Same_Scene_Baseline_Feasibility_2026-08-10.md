# 原始 ReKep“同场景”基线：可执行性审计

日期：2026-08-10  
服务器：`fvl12` (`10.176.53.120:26575`)

## 结论

当前不能诚实地产出“与 CoPE/FSR-PC 的 LIBERO 篮筐场景完全相同的原始 ReKep 实验结果”。这不是负结果，而是实验对象尚未定义且运行依赖不存在：提供的原始 ReKep v2 包只描述 OmniGibson 的 pen/mug/tray 场景，当前 CoPE 实验使用的是 LIBERO/robosuite/MuJoCo 的 `cope_basket_sorting.bddl`。两者没有共同 simulator、scene 或 asset adapter。

因此，本轮没有把 `no_adaptation` 冒充原始 ReKep，也没有把 scripted dry-run 冒充真实 ReKep 结果。

## 已实际完成

- 原始包：`rekep_repair_交接_v2.zip`
- ZIP SHA-256：`f3926073ad4a1c31dccf3943082932cfccc2833c23cc94848654d8f7f1efd8a3`
- 远端只读源包：`/home/lijingsu/rekep_repair_v2_source_f3926073.zip`
- 远端展开目录：`/home/lijingsu/rekep_repair_交接_v2`
- 包内完整性：`SHA256SUMS.txt` 所列 161/161 文件通过。
- 正确设置子进程 `PYTHONPATH` 后，原始包测试：94/94 通过。
- `check_gpu_environment.py --dry-run`：Python、Linux、repair layer、NumPy、SciPy、Matplotlib 通过；GPU 项按设计跳过。
- 同一 seed 的 `pen_insertion` nominal/wrapped/repair 各运行 400-step scripted dry-run；repair trace 产生一次在线 repair，并选择 `Suspend+Retreat+Stabilize+WaitUntilClear+Realign+Resume`。
- dry-run 目录：`/home/lijingsu/rekep_v2_execution_20260810/`。

以上仅证明包内 CPU 逻辑和接线可运行，不是 simulator 行为证据。

## 真实运行阻塞证据

对服务器运行非 dry-run 环境检查，结果为退出码 1：

- 8 张 RTX 3090、driver 535.54.03、PyTorch CUDA 12.1、device count 8、CUDA alloc/add smoke：通过；
- `omnigibson`：不可 import；
- `omni` / Isaac Sim：不可 import；
- `open3d`、`transforms3d`：不可 import；
- 服务器未发现 ReKep checkout、OmniGibson checkout、OmniGibson assets、`rekep_gpu_execution/` 或 `rekep_gpu_analysis/`。

原始包自身还明确保留这些占位项：

- `configs_gpu/machine.yaml` 中的 `<REKEP_ROOT>`、`<OMNIGIBSON_ROOT>`、`<OMNIGIBSON_ASSET_PATH>`、`<OUTPUT_ROOT>`；
- `configs_gpu/adapter_keypoints.yaml` 的 scene-specific keypoint 索引；
- `configs_gpu/tasks.yaml` 的 ReKep OmniGibson JSON scene 路径；
- runner 的真实入口是 `from main import Main` 和 `Main(scene_file=...)`，并不接受 LIBERO BDDL 后端。

原始 runbook 说明 OmniGibson assets 为数十 GB。当前仓库规则禁止在未明确授权时下载巨型资产/检查点，所以本轮没有擅自安装或下载，也没有改写 ReKep/OmniGibson manipulation stack。

## 为什么现有对照不能改名为“原始 ReKep”

| 现有对象 | 不能称为原始 ReKep 的原因 |
|---|---|
| `no_adaptation` | 它是忽略 task-state update 的负对照，不运行 ReKep keypoint constraint solver。 |
| CoPE/FSR-PC 的共享 executor | 使用 privileged simulator-geometry oracle 与 OSC_POSE，不运行 ReKep perception、subgoal/path solver。 |
| 原始包 `--dry-run` | 适配器是 scripted fake；nominal/wrapped 只执行零动作，不能测任务成功。 |
| 原始 ReKep 的 pen/mug/tray 结果 | 即使可运行，也不是当前 LIBERO 篮筐 scene，不能进入“同场景”统计。 |

## 形成可发表同场景 baseline 所需的独立工作包

1. 明确同场景定义：把当前 LIBERO 篮筐资产/目标转换到 OmniGibson，或实现 ReKep→LIBERO 后端；二者结果不可混合。
2. 安装并冻结 ReKep、OmniGibson、Isaac Sim 与授权 assets，记录 commit 和逐资产哈希。
3. 更新真实 pen/holder 或 basket assets 的 keypoint 索引，先通过 nominal ReKep 与 wrapped ReKep parity gate。
4. 将原始 ReKep 的 constraint generation、subgoal solver、path solver 保持只读；只做后端 adapter。
5. 在与 CoPE 相同初始 checkpoint、robot/controller、event schedule、horizon、成功判据和 seeds 上运行；否则只能标为跨平台 case study。
6. 单独报告感知/VLM信息、cached query、solver budget 与 GPU 使用，不能与本轮 privileged-oracle mechanism study 合并。

在这些前提满足前，论文中原始 ReKep 的“同场景结果”应标为未执行，而不是 0% 或用代理方法代填。
