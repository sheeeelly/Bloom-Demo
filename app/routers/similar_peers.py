"""
相似款参考卡 API（封装 az-copilot 属性召回）
  - GET  /api/synthesis/{task_id}/similar-peers
  - POST /api/synthesis/{task_id}/similar-peers/exclude  （兼容旧路径）
  - POST /api/synthesis/{task_id}/similar-peers/mark     （标记相似款）
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.similar_peers import (
    ExcludePeerRequest,
    ExcludePeerResponse,
    GeneratedAttributesResponse,
    SimilarPeersResponse,
)
from app.services import result_store, similar_peers_service

router = APIRouter(prefix="/api/synthesis", tags=["similar-peers"])


def _mark_similar_peer(task_id: str, payload: ExcludePeerRequest) -> ExcludePeerResponse:
    if not payload.goods_id.strip():
        raise HTTPException(status_code=400, detail="goods_id 不能为空")
    probe = similar_peers_service.recall_similar_peers(task_id, refresh=False)
    if probe.error_message == "task_not_found":
        raise HTTPException(status_code=404, detail="合成结果不存在或已过期")
    marked_ids = similar_peers_service.set_exclusion(
        task_id, payload.goods_id, payload.excluded
    )
    task = result_store.get(task_id)
    return ExcludePeerResponse(
        task_id=task_id,
        goods_id=payload.goods_id.strip(),
        excluded=payload.excluded,
        excluded_goods_ids=marked_ids,
        meta={
            "marked_as_similar_style": bool(task.marked_as_similar_style) if task else bool(marked_ids),
            "eligible_for_planning_pool": (
                bool(task.eligible_for_planning_pool) if task else not bool(marked_ids)
            ),
            "action": "mark_similar" if payload.excluded else "unmark_similar",
        },
    )


@router.get("/{task_id}/generated-attributes", response_model=GeneratedAttributesResponse)
def get_generated_attributes(task_id: str) -> GeneratedAttributesResponse:
    """结果页展示：从合成报告解析生成款基本属性（不调 az-copilot）。"""
    resp = similar_peers_service.get_generated_attributes(task_id)
    if resp.error_message == "task_not_found":
        raise HTTPException(status_code=404, detail="合成结果不存在或已过期")
    return resp


@router.get("/{task_id}/similar-peers", response_model=SimilarPeersResponse)
def get_similar_peers(
    task_id: str,
    refresh: bool = Query(False, description="强制重新调用 az-copilot"),
) -> SimilarPeersResponse:
    resp = similar_peers_service.recall_similar_peers(task_id, refresh=refresh)
    if resp.error_message == "task_not_found":
        raise HTTPException(status_code=404, detail="合成结果不存在或已过期")
    return resp


@router.post("/{task_id}/similar-peers/mark", response_model=ExcludePeerResponse)
def mark_similar_peer(task_id: str, payload: ExcludePeerRequest) -> ExcludePeerResponse:
    """标记/取消标记相似款：任务打「相似款」红标，并不再进入选品企划池。"""
    return _mark_similar_peer(task_id, payload)


@router.post("/{task_id}/similar-peers/exclude", response_model=ExcludePeerResponse)
def exclude_similar_peer(task_id: str, payload: ExcludePeerRequest) -> ExcludePeerResponse:
    """兼容旧路径：语义等同 mark。"""
    return _mark_similar_peer(task_id, payload)
