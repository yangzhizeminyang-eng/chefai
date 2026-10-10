"""临时调试：直查 runner 推荐链路的档案加载与响应（用后即删）。"""

import os

os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("LLM_API_KEY", "test-offline")

import uuid

from app.core.db import SessionLocal
from app.graph.runner import load_profile_from_db, run_recommend
from app.models import User


def main() -> None:
    """打印档案加载结果与 run_recommend 原始响应。"""
    anon = f"anon_dbg_{uuid.uuid4().hex[:8]}"
    with SessionLocal() as session:
        user = User(anonymous_id=anon)
        session.add(user)
        session.flush()
        from app.models import Family, FamilyMember

        fam = Family(user_id=int(user.id), name="调试家庭")
        session.add(fam)
        session.flush()
        member = FamilyMember(
            family_id=int(fam.id),
            nickname="调试",
            age_group="18-59",
            allergen_codes=["peanut"],
            no_known_allergen=False,
        )
        session.add(member)
        session.commit()
        user_id = int(user.id)

    print("load_profile_from_db:", load_profile_from_db(SessionLocal(), user_id))

    resp = run_recommend(
        {
            "request_id": f"t_{uuid.uuid4().hex[:12]}",
            "ingredients": ["花生米"],
            "text": "",
            "allergen_codes": [],
            "dietary_restrictions": [],
            "user_id": user_id,
        }
    )
    print("response keys:", sorted(resp.keys()))
    print("results:", len(resp.get("results") or []))
    print("filtered_by:", resp.get("filtered_by"))
    print("partial_failures:", resp.get("partial_failures"))
    print("notice:", resp.get("notice"))
    print("blocked:", resp.get("blocked"), "safe_mode:", resp.get("safe_mode"))

    # 清理
    from sqlalchemy import delete

    with SessionLocal() as session:
        session.execute(delete(Family).where(Family.user_id == user_id))
        u = session.get(User, user_id)
        if u is not None:
            session.delete(u)
        session.commit()
    print("cleaned", anon)


if __name__ == "__main__":
    main()
