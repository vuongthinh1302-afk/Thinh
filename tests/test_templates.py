import json
import tempfile
import unittest
from pathlib import Path

from capcut_templates import spec as S
from capcut_templates.draft import write_draft

ROOT = Path(__file__).resolve().parent.parent


class TestSpec(unittest.TestCase):
    def test_examples_are_valid(self):
        for f in (ROOT / "templates").glob("*.json"):
            errors, _ = S.validate(S.load(f))
            self.assertEqual(errors, [], f.name)

    def test_slots_from_beats(self):
        s = S.from_dict({"name": "x", "slots_from_beats": True,
                         "music": {"beats": [0, 1, 2.5, 4]}})
        self.assertEqual([x.duration for x in s.slots], [1, 1.5, 1.5])
        self.assertEqual(s.duration, 4)

    def test_detects_errors(self):
        s = S.from_dict({"name": "x", "fps": 29, "slots": [{"duration": 1}],
                         "texts": [{"text": "a", "start": 0, "duration": 5}]})
        errors, _ = S.validate(s)
        joined = " ".join(errors)
        self.assertIn("fps", joined)
        self.assertIn("thời lượng", joined)
        self.assertIn("quá hết video", joined)

    def test_unknown_field(self):
        with self.assertRaises(S.SpecError):
            S.from_dict({"name": "x", "slots": [{"duration": 1, "foo": 1}]})


class TestDraft(unittest.TestCase):
    def test_draft_structure(self):
        spec = S.load(ROOT / "templates" / "travel-vlog.json")
        with tempfile.TemporaryDirectory() as tmp:
            folder = write_draft(spec, Path(tmp))
            c = json.loads((folder / "draft_content.json").read_text(encoding="utf-8"))
            self.assertEqual(c["canvas_config"]["width"], 1080)
            self.assertEqual(c["duration"], 11_500_000)
            video = next(t for t in c["tracks"] if t["type"] == "video")
            self.assertEqual(len(video["segments"]), 5)
            ends = [s["target_timerange"]["start"] + s["target_timerange"]["duration"]
                    for s in video["segments"]]
            self.assertEqual(ends[-1], c["duration"])
            ids = {m["id"] for m in c["materials"]["videos"]}
            self.assertTrue(all(s["material_id"] in ids for s in video["segments"]))
            for m in c["materials"]["videos"]:
                self.assertTrue(Path(m["path"]).exists())
            info = json.loads((folder / "template_info.json").read_text(encoding="utf-8"))
            self.assertEqual(len(info["replaceable_slots"]), 5)


if __name__ == "__main__":
    unittest.main()
