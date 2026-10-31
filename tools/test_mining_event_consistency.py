import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"


def load_worker():
    spec = importlib.util.spec_from_file_location("translation_worker_mining_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    worker = load_worker()
    expected = {
        "You uncover a deposit of sphalerite and stake it out.":
            "你發現了一處閃鋅礦礦床，並加以標記。",
        "You begin excavating a deposit of sphalerite.":
            "你開始開採閃鋅礦礦床。",
        "You carefully chip away at a deposit of sphalerite...":
            "你小心翼翼地鑿開閃鋅礦礦床……",
        "You excavate sphalerite ore from a deposit of sphalerite.":
            "你從閃鋅礦礦床中開採出閃鋅礦。",
        "A deposit of sphalerite is depleted.":
            "閃鋅礦礦床已經枯竭。",
        "A deposit of sphalerite has been uncovered and marked here.":
            "這裡有一處已發現並標記的閃鋅礦礦床。",
        "You examine sylvite and determine it is not suitable for lapidary work.":
            "你檢查了鉀石鹽，確認它不適合用於寶石加工。",
        "You drop sylvite.":
            "你丟下鉀石鹽。",
        "You are carrying sphalerite ore.":
            "你正攜帶著閃鋅礦。",
        "Shift appreciates your sacrifice of sphalerite ore.":
            "你將閃鋅礦奉獻給Shift。",
        "You drop an anglesite cluster.":
            "你丟下一簇硫酸鉛礦。",
        "You are carrying a chunk of heartstone.":
            "你正攜帶著一塊心石。",
        "You start crafting a grip from a slab of diorite.":
            "你開始用一塊閃長岩製作握把。",
        "You deeply score a slab of diorite...":
            "你在一塊閃長岩上刻出深痕……",
        "You hammer at a slab of diorite, knocking off the scored pieces to get a basic shape...":
            "你敲打一塊閃長岩，敲掉刻痕處的碎片，塑出基本形狀……",
        "You knock smaller pieces off from a slab of diorite, refining its shape...":
            "你從一塊閃長岩上敲下較小的碎片，進一步修整形狀……",
        "You carefully score shallow grooves into the sides of a slab of diorite...":
            "你小心地在一塊閃長岩側面刻出淺槽……",
        "After a final buff and polish, a diorite grip is complete!":
            "經過最後的打磨和拋光，閃長岩握把就完成了！",
        "You drop a diorite grip.":
            "你丟下閃長岩握把。",
        "You start crafting a grip from a chunk of greenstone.":
            "你開始用一塊綠石製作握把。",
        "You deeply score a chunk of greenstone...":
            "你在一塊綠石上刻出深痕……",
        "You carefully smooth the edges of a chunk of greenstone...":
            "你小心地磨平一塊綠石的邊緣……",
        "After a final buff and polish, a greenstone grip is complete!":
            "經過最後的打磨和拋光，綠石握把就完成了！",
        "Sorry, a chunk of greenstone is not large enough to make grip.":
            "抱歉，一塊綠石不夠大，無法製作握把。",
        "Sorry, a diopside crystal is not large enough to make grip.":
            "抱歉，一顆透輝石晶體不夠大，無法製作握把。",
        "Sorry, a frobnite crystal is not large enough to make grip.":
            "抱歉，一顆frobnite晶體不夠大，無法製作握把。",
        "You start crafting a grip from a chunk of frobnite.":
            "你開始用一塊frobnite製作握把。",
        "After a final buff and polish, a friedelite cup is complete!":
            "經過最後的打磨和拋光，friedelite杯子就完成了！",
        "You deeply score a friedelite cluster...":
            "你在一簇friedelite上刻出深痕……",
        "You knock smaller pieces off from a friedelite cluster, refining its shape...":
            "你從一簇friedelite上敲下較小的碎片，進一步修整形狀……",
        "You drop a friedelite cup.":
            "你丟下friedelite杯子。",
    }
    for source, translated in expected.items():
        assert worker.translate_mining_event_line(source) == translated
        assert worker.deterministic_translate(source) == translated

    source = (
        "You excavate sphalerite ore from a deposit of sphalerite.\n"
        "A deposit of sphalerite is depleted."
    )
    old_cache = "你從閃鋅礦礦床中開采閃鋅礦。\n方鉛礦的儲量正在枯竭。"
    assert worker.normalize_mining_events(source, old_cache) == (
        "你從閃鋅礦礦床中開採出閃鋅礦。\n閃鋅礦礦床已經枯竭。"
    )

    inventory_source = "You are carrying:\nsylvite\nsphalerite ore"
    inventory_old = "你正攜帶著：\n石鹽\n藍晶石礦石"
    assert worker.normalize_mining_events(inventory_source, inventory_old) == (
        "你正攜帶著：\n鉀石鹽\n閃鋅礦"
    )

    completion_source = "After a final buff and polish, a diorite grip is complete!\n+52k xp!"
    completion_old = "經過最後的打磨和拋光，黛瑞石握把就完成了！\n+52k 經驗值！"
    assert worker.normalize_mining_events(completion_source, completion_old) == (
        "經過最後的打磨和拋光，閃長岩握把就完成了！\n+52k 經驗值！"
    )

    # Unknown fictional mineral identifiers remain visible instead of being guessed.
    assert worker.translate_mining_event_line(
        "A deposit of frobnite is depleted."
    ) == "frobnite礦床已經枯竭。"
    print("mining event consistency regression passed")


if __name__ == "__main__":
    main()
