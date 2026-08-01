"""
ModelStore: 训练模型持久化与版本管理
- 保存/加载训练好的模型权重 (pickle)
- 自动版本号 (v1, v2, v3...)
- 模型与训练任务 job_id 映射
- 支持后续选择使用或继续训练
"""
import json
import logging
import pickle
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ModelStore:
    """模型存储与版本管理器"""

    def __init__(self, base_dir: str):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._index_file = self._base / "index.json"
        self._index: dict = self._load_index()

    # ------------------------------------------------------------------
    # 索引管理
    # ------------------------------------------------------------------
    def _load_index(self) -> dict:
        if self._index_file.exists():
            try:
                with open(self._index_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"models": {}, "next_version": 1}

    def _save_index(self):
        with open(self._index_file, "w") as f:
            json.dump(self._index, f, indent=2, ensure_ascii=False)

    def _next_version(self) -> int:
        v = self._index.get("next_version", 1)
        self._index["next_version"] = v + 1
        return v

    # ------------------------------------------------------------------
    # 核心操作
    # ------------------------------------------------------------------
    def save_model(
        self,
        model,
        job_id: str,
        model_class: str,
        handler: str,
        market: str,
        metrics: Optional[dict] = None,
        config: Optional[dict] = None,
    ) -> dict:
        """保存训练好的模型，返回模型元信息"""
        with self._lock:
            version = self._next_version()
            model_id = f"model_v{version}"

            # 创建模型目录
            model_dir = self._base / model_id
            model_dir.mkdir(parents=True, exist_ok=True)

            # 序列化模型权重
            model_file = model_dir / "model.pkl"
            with open(model_file, "wb") as f:
                pickle.dump(model, f)

            # 元信息
            meta = {
                "model_id": model_id,
                "version": version,
                "job_id": job_id,
                "model_class": model_class,
                "handler": handler,
                "market": market,
                "metrics": metrics or {},
                "config": config or {},
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "model_file": str(model_file),
                "size_bytes": model_file.stat().st_size,
            }

            # 写入元信息文件
            meta_file = model_dir / "meta.json"
            with open(meta_file, "w") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            # 更新索引
            self._index["models"][model_id] = {
                "version": version,
                "job_id": job_id,
                "model_class": model_class,
                "handler": handler,
                "market": market,
                "created_at": meta["created_at"],
                "size_bytes": meta["size_bytes"],
            }
            self._save_index()

            logger.info(
                f"Model saved: {model_id} (job={job_id}, class={model_class}, "
                f"size={meta['size_bytes']/1024:.1f}KB)"
            )
            return meta

    def load_model(self, model_id: str):
        """加载模型对象（用于推理或继续训练）"""
        meta = self.get_meta(model_id)
        if not meta:
            raise FileNotFoundError(f"Model {model_id} not found")
        model_file = Path(meta["model_file"])
        if not model_file.exists():
            raise FileNotFoundError(f"Model file not found: {model_file}")
        with open(model_file, "rb") as f:
            model = pickle.load(f)
        logger.info(f"Model loaded: {model_id}")
        return model

    def get_meta(self, model_id: str) -> Optional[dict]:
        """获取模型元信息"""
        meta_file = self._base / model_id / "meta.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def list_models(self) -> list[dict]:
        """列出所有已保存的模型（按版本降序）"""
        models = []
        for model_id, info in self._index.get("models", {}).items():
            meta = self.get_meta(model_id)
            if meta:
                models.append(meta)
        models.sort(key=lambda m: m.get("version", 0), reverse=True)
        return models

    def find_by_job(self, job_id: str) -> Optional[dict]:
        """通过训练任务 ID 查找对应模型"""
        for model_id, info in self._index.get("models", {}).items():
            if info.get("job_id") == job_id:
                return self.get_meta(model_id)
        return None

    def delete_model(self, model_id: str) -> bool:
        """删除模型"""
        import shutil
        with self._lock:
            model_dir = self._base / model_id
            if model_dir.exists():
                shutil.rmtree(model_dir)
            self._index.get("models", {}).pop(model_id, None)
            self._save_index()
            logger.info(f"Model deleted: {model_id}")
            return True


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_model_store: Optional[ModelStore] = None


def get_model_store() -> ModelStore:
    global _model_store
    if _model_store is None:
        from qtrader.backend.config import settings
        _model_store = ModelStore(settings.model_store_dir)
    return _model_store
