# 模块地图

Bloom 是一个本地时装设计工作室。两间工作室共用同一条出图链路和同一间成品库。

```text
作品首页
  ├─ 双爆款合成  gap-fusion
  └─ 趋势改造    design
         │
         ▼
   提示词与设计点
         │
         ▼
   synthesis_service
         │
         ├─ 未开 GPU：界面可走通，不出真图
         └─ 已开 GPU：comfy_client 注入本机密钥 → 工作流出图
         │
         ▼
       成品库 library
```

| 层 | 双爆款合成 | 趋势改造 |
| --- | --- | --- |
| 页面 | `app/static/gap-fusion.html` | `app/static/design.html` |
| 接口 | `POST /api/gap-fusion` | `POST /api/design` |
| 创意输入 | 两件衣服 + 互斥设计点 | 季节趋势包 + 参考衣服 |
| 数据 | `data/weekly_gaps/`、`data/crawler_feeds/`、`data/az_hot_cache.json` | `data/nybfw_packs/` |
| 工作流 | `workflows/product_design_v13.json` | `workflows/fashion_design_api.json` |

密钥只在提交工作流的那一下进入内存：`app/services/comfy_client.py` 读取环境变量，填进空着的 `api_key` 和网关地址。工作流文件本身保持为空。
