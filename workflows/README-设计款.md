# 设计款 / 方案三·四 Comfy 工作流接入说明

## 已放置

| 文件 | 说明 |
|------|------|
| `fashion_design_api.json` | **方案三运行时**：已修复 0.2v 的 API 导出版（面料分析 → 重设计 → GP Image 2 八并发 3:4 2K；`quality=medium`，`input_fidelity=omit`） |
| `fashion_design_ui.json` | 同链路 UI 对照（来源：`AI开款_GPT5.5_…_已修复.json`；**不可**直接 `/prompt`） |
| `product_design_v13.json` | **方案四运行时默认**：竞品+商品直链 API（V13，可注入 intervention_prompt） |
| `product_design_v13_ui.json` | V13 UI（设计点可视化选择）；**不可**直接 `/prompt`，待「导出 API」后切换 |

## 环境变量

```bash
COMFY_FASHION_WORKFLOW_TEMPLATE_PATH=./workflows/fashion_design_api.json
COMFY_GAP_FUSION_WORKFLOW_TEMPLATE_PATH=./workflows/product_design_v13.json
COMFY_V13_UI_WORKFLOW_PATH=./workflows/product_design_v13_ui.json
```

## 方案三注入（`build_fashion_design_workflow`）

1. `LoadImage`（参考图01）← 上传/灵感图  
2. `CloudswayFashionMaterialCraftAnalyzerGPT55.analysis_prompt` ← NYBFW 追加块  
3. `CloudswayFashionBestsellerDesignerGPT55.design_prompt` ← Designer Brief  
4. `SaveImage` 多视图 + `PreviewAny` 报告节点  

## 方案四注入

- Demo：`intervention_prompt` 写入 v9/V12「人工干预 / User Prompt」文本节点  
- V13 UI 合同：节点 57/58 分析设计点、59 可视化勾选（API 导出后对齐）  

## 爬虫 / 报告

- 方案三一期：`data/nybfw_packs/*.json` 人工喂入  
- 方案四一期：`data/weekly_gaps/*.json` 人工结构化  
- 后续爬虫口径见周报种子 `crawler_contract_future`（Demo 不开发）
