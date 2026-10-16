"""Test Audio Master Agent ducking, SFX placement, and J/L cut offsets."""

import unittest
from agents.audio_master_agent import AudioMasterAgent
from agents.schemas import MasterEditPlan, TimelineClipAction, KeyframeTransform


class TestAudioAgent(unittest.TestCase):
    def setUp(self):
        self.audio_agent = AudioMasterAgent()

    def test_calculate_ducking_envelope(self):
        dialogue = [
            TimelineClipAction(
                action_id=1,
                track_type="AUDIO",
                track_index=0,
                source_file_id="voice_01",
                master_filepath="C:/voice.mp4",
                src_in_sec=0.0,
                src_out_sec=5.0,
                timeline_in_sec=1.0,
                reasoning="Speech segment",
            )
        ]

        envelope = self.audio_agent.calculate_ducking_envelope(
            dialogue_actions=dialogue,
            ducked_db=-22.0,
            regular_db=-10.0,
            ramp_sec=0.2,
        )

        self.assertEqual(len(envelope), 4)
        # Pre-duck ramp
        self.assertEqual(envelope[0]["time_sec"], 0.8)
        self.assertEqual(envelope[0]["gain_db"], -10.0)
        # Active duck
        self.assertEqual(envelope[1]["time_sec"], 1.0)
        self.assertEqual(envelope[1]["gain_db"], -22.0)
        # End duck
        self.assertEqual(envelope[2]["time_sec"], 6.0)
        self.assertEqual(envelope[2]["gain_db"], -22.0)
        # Post-duck ramp back to regular
        self.assertEqual(envelope[3]["time_sec"], 6.2)
        self.assertEqual(envelope[3]["gain_db"], -10.0)

    def test_apply_jl_cut_offsets(self):
        # Two consecutive clips from different master files
        v1 = TimelineClipAction(
            action_id=1,
            track_type="VIDEO",
            track_index=0,
            source_file_id="file_A",
            master_filepath="C:/fileA.mp4",
            src_in_sec=0.0,
            src_out_sec=4.0,
            timeline_in_sec=0.0,
            reasoning="Scene A",
        )
        a1 = TimelineClipAction(
            action_id=2,
            track_type="AUDIO",
            track_index=0,
            source_file_id="file_A",
            master_filepath="C:/fileA.mp4",
            src_in_sec=0.0,
            src_out_sec=4.0,
            timeline_in_sec=0.0,
            reasoning="Scene A audio",
        )
        v2 = TimelineClipAction(
            action_id=3,
            track_type="VIDEO",
            track_index=0,
            source_file_id="file_B",
            master_filepath="C:/fileB.mp4",
            src_in_sec=1.0,
            src_out_sec=5.0,
            timeline_in_sec=4.0,
            reasoning="Scene B",
        )
        a2 = TimelineClipAction(
            action_id=4,
            track_type="AUDIO",
            track_index=0,
            source_file_id="file_B",
            master_filepath="C:/fileB.mp4",
            src_in_sec=1.0,
            src_out_sec=5.0,
            timeline_in_sec=4.0,
            reasoning="Scene B audio",
        )

        plan = MasterEditPlan(
            plan_id="jl_test",
            project_title="JL Cut Test",
            timeline_duration_sec=8.0,
            actions=[v1, a1, v2, a2],
        )

        plan = self.audio_agent.apply_jl_cut_offsets(plan, offset_sec=0.25)
        # Audio for scene B should now start at 3.75s (-0.25s J-cut)
        self.assertEqual(a2.timeline_in_sec, 3.75)
        self.assertEqual(a2.src_in_sec, 0.75)
        self.assertEqual(a2.j_l_cut_audio_offset_sec, -0.25)

    def test_place_transition_sfx(self):
        v_punch = TimelineClipAction(
            action_id=1,
            track_type="VIDEO",
            track_index=0,
            source_file_id="file_A",
            master_filepath="C:/fileA.mp4",
            src_in_sec=0.0,
            src_out_sec=3.0,
            timeline_in_sec=2.0,
            keyframes=[KeyframeTransform(time_offset_sec=0.0, scale=108.0)],
            reasoning="Punch in cut",
        )
        plan = MasterEditPlan(
            plan_id="sfx_test",
            project_title="SFX Test",
            timeline_duration_sec=5.0,
            actions=[v_punch],
        )

        plan = self.audio_agent.place_transition_sfx(plan, ["C:/sfx/whoosh.wav"])
        sfx_actions = [a for a in plan.actions if a.track_index == 1 and a.track_type == "AUDIO"]
        self.assertEqual(len(sfx_actions), 1)
        self.assertEqual(sfx_actions[0].master_filepath, "C:/sfx/whoosh.wav")
        # Leads slightly: 2.0 - 0.15 = 1.85s
        self.assertEqual(sfx_actions[0].timeline_in_sec, 1.85)


if __name__ == "__main__":
    unittest.main()
