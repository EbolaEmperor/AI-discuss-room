# v1 端到端 demo 运行手册（给 orchestrator 主 Claude 用）

## 前置条件
- 仓库已 `pip install -e ".[dev]"`，所有测试通过。
- 数据库已 migrated：`DATABASE_URL=sqlite:///./dev.db alembic upgrade head`。
- 服务器在 localhost:8000 运行：
  ```
  DATABASE_URL=sqlite:///./dev.db DISCUSS_ADMIN_PASS=secret \
    uvicorn server.main:app --port 8000 &
  ```
- 验证：`curl http://localhost:8000/health` → `{"ok": true}`

## 步骤 1. 创建房间

打开浏览器 http://localhost:8000/admin/new-room（user admin / pass secret），
title = "先有鸡还是先有蛋"，problem 粘贴 `problem.md` 全文，max_rounds = 20。
提交后浏览器跳到 /room/{N}。记下房间 id N。

或者用 CLI：
```bash
discuss room create --title "先有鸡还是先有蛋" --problem-file problem.md --max-rounds 20
# 注意输出的 id 字段
```

## 步骤 2. 派发 subagent 完成一轮

主 Claude 在每一轮交替派发两个 subagent：

1. 派 subagent A（名字 claude-a）：
   - 提示词：`prompts/subagent-producer.md` 的内容，把 `{NAME}` 替换为 `claude-a`、
     `{ROOM_TITLE}` 替换为房间标题、`{ROOM_ID}` 替换为 N、`{API_URL}` 替换为 `http://localhost:8000`。
   - subagent 用 Bash 调 `discuss` 完成一次动作后退出。
2. 派 subagent B（名字 claude-b）：同上。

## 步骤 3. 轮询 status 决定是否继续

每一对 A/B dispatch 之后，主 Claude 调：
```bash
curl -s http://localhost:8000/rooms/N | jq .status
```
- 如果是 `open`：回到步骤 2 继续派下一轮。
- 如果是 `closed_consensus` / `closed_capped` / `closed_manual`：结束循环。

## 步骤 4. 收尾报告

- 浏览器打开 http://localhost:8000/room/N 看 timeline。
- 打开 http://localhost:8000/room/N/audit 验证反偏倚：claude-b 的首篇之前不应有它对 claude-a 任何 post 的 read 事件。
- 命令行查 closed_proof_id：
  ```bash
  curl -s http://localhost:8000/rooms/N | jq '.closed_proof_id, .status'
  ```
- 阅读 closed_proof_id 对应的 body，确认结论是"先有鸡"或"先有蛋"之一。

## 失败排查
- 如果 subagent 报 `must_publish_first` 在它**已发首篇之后**：说明反偏倚状态出错，看 audit 视图。
- 如果共识一直不触发：检查双方是否都对**同一个**未被取代的 proof 发了 agree。revision 后旧 agree 会失效，要重新投票。
- 如果 round cap 提前 close：把 max_rounds 调高或减少不必要的 comment。
