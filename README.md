# 文档变化监控

每 30 分钟检查两个腾讯表格。程序只对腾讯返回的 `workbook` 和
`related_sheet` 解压后状态生成指纹，不会把每次请求都会变化的时间戳、追踪 ID、
页面脚本或登录页计入比较。

## 安全规则

- 第一次成功抓取只建立基准，不通知。
- 抓取失败、响应为空或结构异常时保留旧快照，不通知。
- 只有已验证的数据状态指纹发生变化时才创建 GitHub Issue。
- `document_changed.flag` 和 `monitor-result.json` 都是临时文件，不提交到仓库。
- 工作流使用并发锁，避免两次定时任务同时修改快照。

## 金山文档

原分享链接目前会跳转到 `account.kdocs.cn` 登录页，GitHub Actions 无法从该链接
读取“懒懒单”的内容。程序不会再把登录页或空字符串当作文档。

如果取得一个无需交互登录、直接返回 CSV/XLSX/原始文件的稳定地址，可在仓库
Actions Secret 中设置：

- `KDOCS_EXPORT_URL`：稳定导出地址；
- `KDOCS_COOKIE`：仅在导出地址确实要求 Cookie 时设置。

没有配置 `KDOCS_EXPORT_URL` 时，金山文档不会参与比较，两个腾讯文档仍正常监控。

## 本地验证

```bash
python -m unittest discover -s tests -v
python monitor.py
python monitor.py
```

第二次运行在文档未修改时必须输出 `NO CHANGE`。
