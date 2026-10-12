"""Meaningful renderer geometry and grammar checks; no encoding in unit tests."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from p2v.renderer import CAPTION, CONTENT, content_point, fit_box, node_state, validate_visual


class RendererTests(unittest.TestCase):
    def test_figure_aspect_and_safe_zone(self):
        box=fit_box((400,1200),CONTENT)
        self.assertAlmostEqual((box[2]-box[0])/(box[3]-box[1]),1/3)
        self.assertGreaterEqual(box[0],CONTENT[0])
        self.assertLessEqual(box[2],CONTENT[2])
        self.assertLess(box[3],CAPTION[1])
        self.assertEqual(content_point(0,0),CONTENT[:2])
        self.assertEqual(content_point(1,1),CONTENT[2:])

    def test_motion_and_visibility_are_relative_to_audio_duration(self):
        node={"id":"cell","x":.8,"y":.4}
        events=[{"target":"cell","kind":"reveal","start":.1,"end":.2},
                {"target":"cell","kind":"move","start":.2,"end":.6,"from_x":.2,"to_x":.8}]
        self.assertEqual(node_state(node,events,0)["opacity"],0)
        state=node_state(node,events,.4)
        self.assertEqual(state["opacity"],1)
        self.assertAlmostEqual(state["x"],.5)
        self.assertAlmostEqual(node_state(node,events,.9)["x"],.8)

    def test_unsupported_kind_and_unresolved_topology_fail(self):
        with self.assertRaisesRegex(ValueError,"Unsupported visual"):
            validate_visual({}, {"visual":{"kind":"automatic_molecule"}})
        scene={"visual":{"kind":"diagram","nodes":[{"id":"a","shape":"cell","x":.3,"y":.4}],"edges":[{"source":"a","target":"missing"}]}}
        with self.assertRaisesRegex(ValueError,"existing diagram nodes"):
            validate_visual({},scene)
        scene["visual"]["edges"]=[]
        scene["visual"]["nodes"][0]["shape"]="invented_topology"
        with self.assertRaisesRegex(ValueError,"Unsupported node shape"):
            validate_visual({},scene)

    def test_invalid_focus_and_escaping_asset_path_fail(self):
        project={"render":{"assets":{"a":{"path":"fig.png"}}}}
        scene={"visual":{"kind":"figure","asset":"a","focus":[.5,0,.5,1]}}
        with self.assertRaisesRegex(ValueError,"positive width"):
            validate_visual(project,scene)
        project["render"]["assets"]["a"]["path"]="../private.png"
        with self.assertRaisesRegex(ValueError,"inside the project"):
            validate_visual(project,scene)

    def test_nested_draft_render_settings(self):
        project={"project":{"render":{"assets":{"a":{"path":"fig.png"}}}}}
        result=validate_visual(project,{"visual":{"kind":"figure","asset":"a"}})
        self.assertEqual(result["asset"],"a")


if __name__=="__main__":
    unittest.main()
