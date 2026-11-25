from nexus.inference.engine import BlockCapacity, ModelProfile, plan_pipeline


def test_infeasible_without_gpu():
    model = ModelProfile(name="m", layers=32, params_billion=8)
    blocks = [BlockCapacity(block_id="b1", name="b1", online=True, gpu_count=0, vram_total_mb=0)]
    plan = plan_pipeline(model, blocks)
    assert plan.feasible is False
    assert plan.reasons


def test_infeasible_when_vram_too_small():
    model = ModelProfile(name="m", layers=32, params_billion=70)
    blocks = [BlockCapacity(block_id="b1", name="b1", online=True, gpu_count=1, vram_total_mb=8000)]
    plan = plan_pipeline(model, blocks)
    assert plan.feasible is False


def test_feasible_split_across_blocks():
    model = ModelProfile(name="big", layers=40, params_billion=8, kv_cache_mb_per_1k_ctx=64, context_len=4096)
    blocks = [
        BlockCapacity(block_id="b1", name="b1", online=True, gpu_count=1, vram_total_mb=16000),
        BlockCapacity(block_id="b2", name="b2", online=True, gpu_count=1, vram_total_mb=16000),
    ]
    plan = plan_pipeline(model, blocks)
    assert plan.feasible is True
    assert sum(s.layers for s in plan.stages) == model.layers
    assert len(plan.stages) == 2


def test_never_claims_single_gpu():
    model = ModelProfile(name="m", layers=10, params_billion=1)
    blocks = [
        BlockCapacity(block_id="b1", name="b1", online=True, gpu_count=1, vram_total_mb=24000),
        BlockCapacity(block_id="b2", name="b2", online=True, gpu_count=1, vram_total_mb=24000),
    ]
    plan = plan_pipeline(model, blocks)
    assert plan.strategy == "pipeline"
    assert any("pipeline" in w.lower() for w in plan.warnings)
