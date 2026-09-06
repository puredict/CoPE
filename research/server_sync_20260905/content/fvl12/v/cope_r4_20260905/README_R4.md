# CoPE / FSR-PC R4：第一轮修复与复跑

本目录是在原 R3 交接代码上修改的实验版本。原 R3 服务目录和输出不变。

入口是 `scripts/run_r4_lineage.py`，不要使用旧 `run_r3_lineage.py` 的困难条件 80% generation gate 作为 R4 评测门槛。

- 修改范围、预算和边界：[docs/R4_PROTOCOL.md](docs/R4_PROTOCOL.md)。
- 本次修改、服务及运行结果：[docs/R4_RUN_LOG_2026-09-04.md](docs/R4_RUN_LOG_2026-09-04.md)。
- 实际安装版本的结构化解码兼容性：[docs/schema_compatibility_gate.md](docs/schema_compatibility_gate.md)。

## 验证

```bash
PYTHONPATH=code python3 -m unittest discover -s tests_r4 -v
PYTHONPATH=code python3 -m unittest discover -s tests_r3 -v
```

`--client oracle` 只用于代码或物理底座检查，其字符长度估计和结果绝不能作为真实模型实验。

## 开发运行

```bash
python scripts/run_r4_lineage.py \
  --budget fixed --mode free_running --split development \
  --seeds 1000 --profiles calibration \
  --base-url http://127.0.0.1:8000 \
  --backend symbolic_basket --out /absolute/new/output_directory
```

上述命令是符号执行；真实物理执行必须在配置好的 LIBERO 环境中选择 `--backend libero_mujoco`。`reference_diagnostic` 是每一步提供正确前态的单步诊断，不能报告其端到端成功率。所有运行目录必须不存在，禁止覆盖已有结果。

充分预算首先运行 `audit_r4_capacity.py` 做实际 tokenizer 容量检查，再用 `collect_r4_throughput.py` 提取同一服务实例的真实开发吞吐，最后重新审计并冻结配置。`adequate` 为 null 或状态仍为 pending 时 runner 会拒绝启动；正式测试还需要显式的开发验收与协议冻结。

运行时的逐事件 semantic flags 是相对于该方法实际前态的局部检查，不代表整个已提交轨迹没有继承早先的错误。完整轨迹结论必须补充 `scripts/audit_r4_trajectory.py --episode /absolute/episode --out /absolute/new/audit.json` 的独立全局审计：从初始状态重建 gold，比较每次提交及最终根、计划、生命周期和未涉及记录。审计不会修改运行结果，也不会用 gold 修正模型状态。`reference_diagnostic` 不适用这个连续轨迹审计。

Generic Patch、不同恢复对象、多订单与真实动作边界中断属于第二轮，当前没有实现，不能从本轮两方法的结果推断这些结论。
