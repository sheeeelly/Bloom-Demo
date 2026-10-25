# 双爆款合成

把两件爆款收成一件新衣服。

适合这种问题：一件衣服的廓形在卖，另一件的领和细节也在卖，下一件能不能同时带上两边，而不是做成拼贴。

## 操作

1. 在双爆点板上，为两件衣服各选一组设计点。同一维度只能留一个，两边不能抢同一个维度。
2. 各选一件爆款。选中后勾选这件衣服上要留下来的属性。
3. 点「生成新款」。设计点分析和提示词在后台完成。
4. 到成品库看这件新款。

## 系统在做什么

| 步骤 | 代码 |
| --- | --- |
| 读演示爆点与两件候选 | `app/services/gap_fusion_prompt.py` |
| 外部爆款列表 | `app/services/crawler_weekly_adapter.py` |
| 另一侧爆款列表 | `app/services/az_hot_service.py` |
| 同维互斥 | `app/services/hotspot_mutex.py` |
| 设计点 | `app/services/v13_design_points.py` |
| 创建生成任务 | `app/routers/gap_fusion.py` → `app/services/synthesis_service.py` |
| 出图 | `workflows/product_design_v13.json` |

样例索引在 `data/gallery/manifest.json`，成图在 `app/static/gallery/`。
