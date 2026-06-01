# 最小重建规则

## 原则
- 仅重建受影响组件，禁止默认全量重建。
- 变更范围不明确时，先按最小集合执行，再按需补充。

## 命令映射
- 仅 `web/` 或 `host/` 变更：`./rebuild.sh host`
- 仅 `agent/` 变更：`./rebuild.sh agent <user_id>`
- 同时有 `web/host` 与 `agent` 变更：先 `./rebuild.sh host`，再 `./rebuild.sh agent <user_id>`

## 何时允许 full / infra
- `./rebuild.sh full`：仅在需要同时重建 host+agent 且需要重新应用整体编排时使用。
- `./rebuild.sh infra`：仅在基础设施异常或配置变更涉及 `postgres/tei/host` 基础依赖时使用。

## 明确禁止
- 未确认必要性时，不得因 `agent` 或 `web/host` 代码改动重启 `tei/postgres`。
- 未给出 `user_id` 时，不得批量重建全部用户容器。
