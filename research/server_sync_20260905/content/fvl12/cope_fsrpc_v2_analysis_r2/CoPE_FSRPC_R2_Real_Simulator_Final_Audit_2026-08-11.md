# CoPE / FSR-PC r2 真实模拟器最终审计

执行日期：2026-08-10–11（Asia/Shanghai）  
服务器：`fvl12`，个人账户 `lijingsu`  
证据层级：LIBERO / robosuite / MuJoCo mechanism study

## 最终结论

本轮完成了 final-v8 的 controller gate、Stage B/C/D 共 150 个中断 episode，以及逐 episode 的只读重算、候选隔离检查和视频审计。B、C、D 各自的七项内置 acceptance 全部通过，315/315 个注册事件均交付，150/150 个主实验 episode 均 completed、valid、evaluable，且无 controller 或 infrastructure failure。

科学结论不是“CoPE 全面胜出”：

- **对强 FSR-PC 的行为优势：未观察到。** Stage B 的 CoPE 与 FSR-PC 都是 17/20；Stage C 的 CoPE、FSR-PC、stable-IDs、provenance 全部是 9/15。每个配对 seed/condition 的 task-success 都相同。
- **生命周期/lineage 的行为优势：未观察到。** Stage C 四方法的 lifecycle legality 和 lineage correctness 都是 15/15；I5 中所有方法始终最多只有一个活跃 butter goal。更严重的是，I5 每个方法均为 0/5 adaptation-valid，因此不能用 I5 宣称成功恢复优势。
- **局部编辑/identity 的表示优势：存在。** CoPE 与 stable-IDs 为 identity 15/15；vanilla FSR-PC 与 provenance-only FSR-PC 为 0/15。CoPE pooled normalized edit distance 为 0.43342，三种 FSR-PC 都为 1.0。但该差异没有转化为本任务的成功率优势。
- **审计优势：存在，但主要由 provenance 解释。** CoPE pooled audit coverage 为 1.0；vanilla/stable-IDs 为 0.34433；显式 provenance 版本达到 0.93333，只在 I5 的“哪个目标被取消”查询上留下 0.2 的单条件缺口。因此不能把全部 audit 差异归因于 local editing 本身。
- **rollout verifier 的决策作用：存在；安全或成功优势：未观察到。** verifier 改变了 33/35 个事件的候选选择并拒绝 33 个候选，但两个 arms 都是 9/15 task success，碰撞/unsafe-contact 都为 0。
- **相对 no-adaptation 的描述性收益：明显，但小样本 cluster 推断不足。** CoPE 为 17/20，no-adaptation 为 3/20；episode-level exact McNemar `p=0.000122`。然而四个 condition 复用了同五个 seed，按 seed 聚类后只有 5/5 正向 cluster，双侧 sign test `p=0.0625`，不能按 20 个独立样本过度宣称。
- **原始 ReKep 同场景结果：未执行，不能用代理结果代填。** 提供的 ReKep 包是 OmniGibson pen/mug/tray 接口，而本实验是 LIBERO basket-sorting；服务器缺少 ReKep/OmniGibson/Isaac Sim/assets，也没有 ReKep→LIBERO adapter。`no_adaptation`、共享 executor 和 scripted dry-run 都不是原始 ReKep。

此外，用户要求的强状态变化检查不是 315/315，而是 **314/315**。唯一例外是 `no_adaptation/I3/seed_00/I3-u2`：外部事件已注册、交付和分类，但该负对照按定义不更新 method task state，而候选全拒绝后 simulator 也没有移动。这一例外没有被内置七项 acceptance 捕获，故在本报告单独列为协议缺口。

## 1. 环境与冻结 provenance

| 项目 | 实际值 |
|---|---|
| Host / OS | `fvl12`; Ubuntu 22.04.5 LTS; kernel 5.19.0-50-generic |
| GPU inventory | 8 × NVIDIA GeForce RTX 3090; driver 535.54.03; driver CUDA compatibility 12.2 |
| 本轮 B/C/D GPU 使用 | **无**；GPU compute=false，rendering=CPU OSMesa |
| Python | 3.10.12，`/home/lijingsu/vla/.venv/bin/python` |
| LIBERO | distribution 0.1.0；source commit `570d78333ee977c8ae6de3d97120b23272c4c660` |
| robosuite / MuJoCo | 1.4.1 / 2.3.7 |
| PyTorch | 2.5.1+cu121；未用于 B/C/D 推理 |
| Robot / controller | OnTheGroundPanda / OSC_POSE |
| Controller information | privileged simulator-geometry oracle；learned policy=false |
| Task | `configs_gpu/cope_basket_sorting.bddl`；milk、cream-cheese-as-yogurt、butter 三物体篮筐任务 |
| Horizon | episode 900 steps；candidate 200 steps；control dt 0.05 s |
| Video | agentview，128×128，20 fps |
| Paired seeds | 0–4；nominal gate seeds 0–9 |

最新用户 ZIP 是 `cope_fsrpc_交接_v2(1).zip`，SHA-256：

`4276d9ec8d87d9a7370109da00771fae4b241e518f70f00ee9c3b6d347a39be5`

final-v8 source：

- commit：`b9e4d1ab3fe86a411305c680de102e19353a550d`
- tree：`5cb128b7016d382272aafefd5c706d2c17b92da2`
- branch：`codex/r2-real-execution`
- post-run working tree：clean
- task config SHA-256：`58ce269b4bfcf09d82b77b3acf9c465613e25fe3b88440ae3773e2a3ef7bbf8f`
- BDDL SHA-256：`f0c08a9c870f0a52cde6cc0900c6ab5bd8a1a88dcd1ab7a88bc76fe4df1b10a8`

相对交接包原 commit `37bed33a`，只修改了 real-run/audit harness 的四个文件：`backend_episode.py`、`failure_layers.py`、`run_cope_pilot.py`、`test_postaudit_fixes.py`。ConstraintState、ConstraintSlot、typed patch operators、CoPE policy、所有 FSR-PC policies、repair bridge 和 `rekep_repair` core 的 diff 均为空。

## 2. Tests、dry-run 与 controller gate

交接文档中的 `321` 是原开发仓库的 94 个 frozen repair-core tests 加上 ZIP 内 227 个 standalone tests，不是 ZIP 单独可复现的测试数。本轮口径如下：

- 原样 ZIP standalone：227/227。
- final-v8 audit tree：239/239，2.36 s。
- 单独提供的原始 ReKep repair 包：94/94。
- final-v8 dry-run：75/75 episodes、150/150 events；强制所有 grasp 失败时，I2/I4/I5 仍分别交付 2/2、2/2、3/3 events。

最终 commit 的独立 nominal confirmatory gate 写入新目录，没有覆盖旧 gate：

- 10/10 final task success；
- milk、yogurt、butter 各 10/10 grasp；
- 三物体各 10/10 placement；
- 0 controller、adaptation、infrastructure failure。

## 3. 分母与事件完整性

| Stage | attempted / completed / evaluable | events | adaptation-valid | controller-valid | task-success |
|---|---:|---:|---:|---:|---:|
| B | 60 / 60 / 60 | 105 / 105 | 32 | 60 | 37 |
| C | 60 / 60 / 60 | 140 / 140 | 28 | 60 | 36 |
| D | 30 / 30 / 30 | 70 / 70 | 14 | 30 | 18 |
| **主实验合计** | **150 / 150 / 150** | **315 / 315** | **74** | **150** | **91** |

Failure layer 合计：70 `none`、76 `adaptation`、4 `task`、0 `controller`、0 `infrastructure`。没有 episode 被静默排除。

165/165 个 u2/u3 事件都满足 `scheduled_step = actual_u1_delivery_step + registered_delta`，并且 `delivery_failure_reason` 为空。B 的 I2 和 I4 分别为 15/15；因此 restore 不再依赖 `g_milk.completed` 或任意目标完成。

## 4. Stage B：regression pilot

| Method | I1 | I2 | I3 | I4 | pooled success | pooled adaptation-valid |
|---|---:|---:|---:|---:|---:|---:|
| CoPE | 5/5 | 5/5 | 5/5 | 2/5 | 17/20 | 14/20 |
| FSR-PC | 5/5 | 5/5 | 5/5 | 2/5 | 17/20 | 14/20 |
| no-adaptation | 0/5 | 3/5 | 0/5 | 0/5 | 3/20 | 4/20 |

CoPE 与 FSR-PC 的 20 个 task-success pairs 全部相同，exact McNemar `p=1`。两者 simulator steps 完全相同；wall-clock adaptation latency 差为 0.00053 s，seed-cluster bootstrap 95% interval `[-0.0161, 0.0149]`。

CoPE 相对 no-adaptation 有 14 个 CoPE-only successes、0 个 control-only successes、6 ties。这个对比说明“响应修订”优于“忽略修订”，但不是 CoPE 相对完整重生成方法的证据；并且五个 seed cluster 的 `p=0.0625` 不支持强小样本推断。

一个重要分层现象是：I2 中 CoPE/FSR-PC 都为 5/5 task success，但只有 2/5 adaptation-valid；三个 seed 的 restore repair pipeline 进入 `missing_repair_stage`，最终几何任务仍成功。终态成功因此不能替代 pipeline-valid 分母。

## 5. Stage C：强 FSR-PC 诊断

四方法的任务结果完全相同：

| Method | I3 success / adapt-valid | I4 success / adapt-valid | I5 success / adapt-valid | pooled success |
|---|---:|---:|---:|---:|
| CoPE | 5/5 / 5/5 | 2/5 / 2/5 | 2/5 / 0/5 | 9/15 |
| FSR-PC | 5/5 / 5/5 | 2/5 / 2/5 | 2/5 / 0/5 | 9/15 |
| FSR-PC stable-IDs | 5/5 / 5/5 | 2/5 / 2/5 | 2/5 / 0/5 | 9/15 |
| FSR-PC provenance | 5/5 / 5/5 | 2/5 / 2/5 | 2/5 / 0/5 | 9/15 |

每个 CoPE 对比均有 15/15 outcome ties，exact McNemar `p=1`。零 discordance 不等于已证明等价：若把 15 pairs 当独立样本，真实 discordance rate 的 one-sided 95% 上界仍约 18.1%；若只承认五个 seed clusters，上界约 45.1%。

### 5.1 Identity、lifecycle、lineage

- identity preserved：CoPE 15/15；stable-IDs 15/15；vanilla FSR-PC 0/15；provenance-only 0/15。
- lifecycle transitions legal：四方法均 15/15。
- lineage correct：四方法均 15/15。
- stale-goal execution、cancelled-goal violation、duplicate completion、invalid restore、collision：所有方法均为 0。
- I5 的所有事件前后 snapshot 中，活跃 butter goal 最大数为 1；没有同时活跃的不兼容目标。

因此 stable IDs 关闭了 identity 指标差异；I5 没有产生 lifecycle/lineage 行为优势。CoPE 的优势是保存了显式的 `Suspend → Override → Expire → Revalidate → Restore` 历史，但本轮 downstream repair 在 I5 u3 对所有方法都出现 `missing_repair_stage`。

### 5.2 State churn 与 audit coverage

Stage C pooled：

- CoPE normalized edit distance：0.43342；所有 FSR-PC：1.0。
- CoPE−FSR-PC 差：−0.56658，five-seed cluster bootstrap 95% interval `[-0.58733, -0.54583]`。
- CoPE audit coverage：1.0。
- vanilla/stable-IDs：0.34433；CoPE 差 +0.65567。
- provenance：0.93333；CoPE 差仅 +0.06667。

I5 的 audit coverage 为 CoPE 1.0、vanilla 0.2、stable-IDs 0.2、provenance 0.8。provenance 版本回答了 completed preservation、suspension reason、restore condition 和 replacement state，但没有保留 Q1 cancellation identity。结果支持“原生 persistent history 更容易审计”的窄结论；不能支持“只有局部编辑才能审计”的强结论。

## 6. Stage D：rollout verifier

两个 arms 都是 I3 5/5、I4 2/5、I5 2/5，总计 9/15；adaptation-valid 都是 7/15。没有 collision 或 unsafe-contact。

Verifier 完整性：

- `CoPE_full`：89 candidates evaluated，56 accepted，33 rejected。
- `no_rollout_verification`：91 candidates generated，0 evaluated，0 verifier rejection。
- 89/89 JSONL rows 都具备 canonical `candidate_id/event_id/checkpoint_hash/rollout_start_hash/collision/unsafe_contact/handoff_error/restore_valid/accepted/rejected/rejection_reason` 字段。
- 89/89 `checkpoint_hash == rollout_start_hash == restore_hash`，`restore_exact=true`；同一 episode/event 内所有候选起点一致。
- 33 rejects 中 30 restore-invalid；reasons 为 27 次 `reacquiretarget#1` timeout、6 次 `reacquiretarget#2` timeout。
- accepted handoff error 平均 0.00150 m；rejected 平均 0.28647 m。
- 候选集模式为 18 个 `AAA`、2 个 `A`、9 个 `R`、6 个 `RRRR`；没有任何同一事件内 mixed accept/reject，更没有“坏、坏、好”的自然案例。
- 选择在 33/35 event pairs 中不同：I3 10/10、I4 8/10、I5 15/15；safe-fallback decision 只在 2/35 中不同。

`CoPE_full` 比 no-verification 平均少 32.2 simulator steps，cluster bootstrap 95% interval `[-50.07, -12.27]`；但 wall-clock adaptation latency 多 10.67 s，interval `[8.24, 13.24]`。后者受三路并发和共享主机负载影响，不能作为严格 compute benchmark。

结论是 verifier 确实改变候选决策和执行长度，并能识别高 handoff error；当前场景没有提供任务成功或安全事件优势，也没有展示同一候选集内部的部分分辨。

## 7. Fairness、状态与视频审计

所有 50 个 adaptive paired blocks 通过相同 backend config、initial simulator checkpoint、registered schedule、fairness fingerprint、exogenous event inputs、pre-treatment input/repair goal/candidate set 和 candidate budget 检查：B 20/20、C 15/15、D 15/15。

Post-treatment equality 不作为公平性前提，因为它是被测 update/verifier 的结果：

- B：inputs 20/20，repair goals 20/20；
- C：inputs 13/15，repair goals 12/15；
- D：inputs 2/15，repair goals 13/15。

状态证据：

- 315 个主实验事件中，280 个 adaptive-arm events 的 method task state 前后变化。
- 180 个事件实际移动/移除/恢复 basket；180/180 pre-event 与 post-world hashes 不同，且都有显式 before/after qpos。
- “simulator hash 或 method task state 至少一项变化”为 314/315；唯一例外是上述 no-adaptation I3 seed 0 u2。
- 160/160 episodes 的 task-success 已用几何 predicate、cancellation、collision、object stability、gripper attachment 和 final-settle gate 独立重算，与 result/layer/denominator 四处标签一致。

Artifact 与视频：

- 160 个真实 episode（10 gate + 150 主实验）各有完整九件套；加四个 stage summaries，共 1,444 files。
- 160/160 `video.mp4` 已用 ffmpeg 从头到尾解码，0 failures。
- 分层视觉抽查覆盖 B 的 CoPE/no-adaptation I1/I4、C 的四个 I5 methods、D 的两个 verifier arms，以及 success/failure seeds；终态均与 JSON 几何标签一致，未观察到遗漏的碰撞。
- 结果目录已 `chmod -R a-w`；可写条目为 0。

## 8. 原始 ReKep 同场景基线

详细证据见 [ReKep 同场景可执行性审计](ReKep_Same_Scene_Baseline_Feasibility_2026-08-10.md)。简要结论：

- 原 ReKep ZIP SHA-256：`f3926073ad4a1c31dccf3943082932cfccc2833c23cc94848654d8f7f1efd8a3`。
- 包内 161/161 hashes 与 94/94 tests 通过；scripted `pen_insertion` dry-run 可运行。
- 服务器有可用 CUDA GPU，但缺 `omnigibson`、`omni`/Isaac Sim、Open3D、transforms3d、ReKep checkout、OmniGibson assets。
- 原包的 scene、keypoints 和 runner 针对 OmniGibson pen/mug/tray；当前任务是 LIBERO BDDL basket scene。不存在共同 simulator/asset/backend adapter。
- 未下载数十 GB assets，未把 scripted fake、`no_adaptation` 或共享 privileged executor 改名为“原始 ReKep”。

因此本轮原始 ReKep 的同场景单元格应标为 **not executed / backend undefined**，而不是 0% 或 proxy result。

## 9. Reviewer-style 限制与下一步

1. 这是单一 LIBERO task、五个固定 seed clusters 的 mechanism study，不是跨任务泛化实验。
2. Controller 使用 simulator geometry oracle，没有 perception/VLM/learned policy uncertainty；不能外推到完整机器人系统。
3. I5 对所有方法 0/5 adaptation-valid，是当前最关键的 shared downstream failure。修复这一 method-independent repair-stage contract 后必须重新预注册并重跑 I5，现有 I5 不能支撑 lifecycle superiority claim。
4. Audit coverage 是基于预定义查询和方法 trace 的机制指标；provenance baseline 已证明它容易被显式日志关闭大部分差距。需要独立 evaluator 或使用者审计任务验证外部效度。
5. Verifier 没有 mixed candidate discrimination，也没有 collision/unsafe-positive cases。下一轮应设计保持同一起点、但候选在真实接触安全或 restore validity 上异质的事件，而不是只增加 seeds。
6. Wall-clock latency 受共享主机与并发影响；仅 simulator steps 和固定 budget 可作为本轮较可靠的效率证据。
7. B 的 314/315 强状态变化缺口说明内置 acceptance 不够完整。下一版应把“external task oracle changed，或 physical simulator state changed”作为独立必过 gate，同时保留 no-adaptation method state 不变的定义。
8. 原始 ReKep 需要一个独立、冻结的 ReKep→LIBERO adapter 或完整 OmniGibson scene port。两种路线不可与当前数据混为同场景统计。

当前最稳妥的论文表述是：**CoPE 在本机制任务中产生更局部、identity-preserving、原生可审计的状态更新；但相对完整 FSR-PC 及其强变体，没有观察到任务成功、lifecycle/lineage correctness 或 verifier safety 优势。**

## 10. 结果位置与完整性

远端 source：

`/home/lijingsu/cope_fsrpc_交接_v2_r2`

最终结果：

- Gate：`/home/lijingsu/cope_fsrpc_v2_execution_r2/stage_a_controller_gate_final_v8`
- Stage B：`/home/lijingsu/cope_fsrpc_v2_execution_r2/stage_b_regression_pilot_final_v8`
- Stage C：`/home/lijingsu/cope_fsrpc_v2_execution_r2/stage_c_diagnostic_pilot_final_v8`
- Stage D：`/home/lijingsu/cope_fsrpc_v2_execution_r2/stage_d_verifier_ablation_final_v8`

每个视频位于：

`<stage>/<method>/<condition>/seed_XX/video.mp4`

原始 ReKep dry-run：

`/home/lijingsu/rekep_v2_execution_20260810/`

最终 SHA-256 manifest：

`/home/lijingsu/cope_fsrpc_v2_analysis_r2/final_v8_result_artifacts_sha256.txt`

Manifest 共 1,444 行，其自身 SHA-256：

`6998bf3736d4a56564317888b8dbae8f68a4fc4a8331cc75a30998f097be51b7`

结构化汇总见同目录下的 aggregate metrics 与 paired statistics CSV；所有主结论均从 episode-level JSON/JSONL 重算，而非直接抄 stage summary。
