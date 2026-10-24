# CONTRIBUTING

## 前置

1. 读 `AGENTS.md`（硬规则）与本文件。
2. 读 `docs/audit/research-baseline-audit.md` 了解证据体系与标记。
3. 认领任务前看 `docs/backlog/tasks/` 对应 Task 的验收标准与 open_questions。

## 认领与开发

- 在 Issue/PR 标题引用 `TASK-XXXX` 与 `FEATURE-ID`。
- 分支命名：`feat/TASK-0012-rx-attachments`。
- 依赖 `open_questions` 中未决项的实现，先标记 `PROVISIONAL` 并链接问题；不得编造规则。
- backlog 变更：编辑 `tools/backlog_tasks.py` → `python3 tools/gen_backlog.py` → 提交全部生成物。

## 提交前检查

```bash
python3 tools/validate_baseline.py     # 基线/追踪一致性
python3 tools/gen_backlog.py --check   # 生成物无漂移
npx @redocly/cli lint docs/api/openapi.yaml   # 若改动 API 契约
# + 项目测试（实现代码出现后补充）
```

## PR 要求

- 描述：动机、覆盖 Feature、验证证据（命令+输出/截图-脱敏）、遗留 UNKNOWN。
- 不含：PHI、秘钥、EasyRx 私有素材、未审计的新依赖。
- 评审重点：越权路径、幂等、文件不可变性、审计落点、标记是否被悄悄移除。

## 代码风格（前瞻约定）

- 紧凑、少嵌套；错误处理在边界层；注释引 Feature ID，不复述代码。
- 默认英文标识符；用户可见文案中英由产品层管理。

## 许可证

**未定**——见 `docs/architecture/adr/0007-license-strategy.md`。Gate 未过前提交即表示你同意贡献物暂不授予任何复用许可，待许可证选定后适用于全部历史贡献（将要求贡献者确认 CLA/DCO）。
