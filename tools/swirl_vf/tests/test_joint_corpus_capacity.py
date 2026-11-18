from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from joint_capacity_report import capacity


class CorpusCapacityTests(unittest.TestCase):
    def test_base_aliasing_is_counted_and_no_file_size_is_extrapolated(self):
        a=capacity(10,8)
        self.assertEqual(a['aliasing_base_to_one_patch_glyph_lower_bound'],66)
        self.assertEqual(a['retaining_original_base_plus_all_patches_glyph_count'],74)
        self.assertTrue(a['capacity_fits_even_with_base_aliasing'])
        self.assertFalse(capacity(20000,10000)['capacity_fits_even_with_base_aliasing'])
        self.assertIsNone(a['projected_full_font_bytes'])
        with self.assertRaises(ValueError):capacity(10,11)


if __name__=='__main__':unittest.main()
