"""Operand subroutines preserve decoded curves and the complete varstore state."""
import io
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from fontTools.ttLib import TTCollection, TTFont
from fontTools.misc.psCharStrings import calcSubrBias
sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'tools'),
               str(Path(__file__).resolve().parents[1]/'platform')]
from cff2_expression_pool import ExpressionPool
from probe_polynomial_clamp import build_control
from test_coretext_extract import make_fixture
from cff2_geometry import source_commands, operands, control_points


class ExpressionPoolTests(unittest.TestCase):
    def test_shared_operands_preserve_three_axis_and_clamp_evaluation_after_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'template.ttc';make_fixture(path)
            with TTCollection(path) as collection:
                ordinary,boxes=build_control(collection.fonts[0])
                shared,_=build_control(collection.fonts[0],share_expressions=True)
            subroutines = shared['CFF2'].cff.GlobalSubrs
            bias = calcSubrBias(subroutines)
            def executed_tokens(string):
                index, previous, count = 0, None, 1  # implicit return/end
                while True:
                    token, _, index = string.getToken(index)
                    if token is None: return count
                    count += 1
                    if token == 'callgsubr': count += executed_tokens(subroutines[int(previous)+bias])
                    previous = token
            maximum = max(executed_tokens(s) for s in shared['CFF2'].cff.topDictIndex[0].CharStrings.values())
            self.assertEqual(maximum, shared._swirl_expression_pool_report['maximum_interpreter_operations'])
            a,b=io.BytesIO(),io.BytesIO();ordinary.save(a);shared.save(b)
            self.assertLess(len(b.getvalue()),len(a.getvalue()))
            self.assertGreater(shared._swirl_expression_pool_report['shared_expressions'],0)
            with TTFont(io.BytesIO(a.getvalue())) as original,TTFont(io.BytesIO(b.getvalue())) as packed:
                for table in ('fvar','avar','GSUB','hmtx','vmtx','cmap'):
                    self.assertEqual(original.getTableData(table),packed.getTableData(table))
                rng=np.random.default_rng(2026110411)
                for index,box in enumerate(boxes):
                    for point in box.from_local(rng.uniform(0,1,(16,3))):
                        loc={tag:float(value) for tag,value in zip(('WDTH','wght','HGHT'),point)}
                        # Explicit normalized hidden coordinates exercise the
                        # operand helpers independently of the avar2 mapper.
                        loc.update({f'H{i:03d}':float(rng.uniform(-1,1)) for i in range(4)})
                        name=f'box{index}'
                        left=operands(source_commands(original.getGlyphSet(location=loc,normalized=True)[name]))
                        right=operands(source_commands(packed.getGlyphSet(location=loc,normalized=True)[name]))
                        self.assertEqual(left[0],right[0])
                        np.testing.assert_array_equal(control_points(*left),control_points(*right))

    def test_region_count_and_side_effects_are_part_of_the_helper_contract(self):
        pool=ExpressionPool()
        program=[0,1,2,3,1,'blend']
        self.assertIs(pool.intern(program,3),pool.intern(program,3))
        self.assertIsNot(pool.intern(program,3),pool.intern(program,4))
        for program in ([0,'vsindex'],[0,0,'rmoveto'],[0,'callgsubr']):
            with self.assertRaisesRegex(ValueError,'preserve_variation_and_drawing_state'):
                pool.intern(program,3)

    def test_oversized_program_is_chunked_at_drawing_operators(self):
        pool=ExpressionPool(maximum_helpers=0)
        tokens=[.125]
        for _ in range(100):tokens=[.125,*tokens,0,0,1,'blend']
        expression=pool.intern(tokens,3)
        # This valid nested blend leaves exactly one operand. Disable sharing
        # to force real drawing-chunk boundaries even for repeated expressions.
        program=[0,'vsindex']
        for _ in range(1000):program.extend((expression,expression,'rmoveto'))
        strings,subroutines,report=pool.compile({'probe':program})
        self.assertGreater(report['drawing_chunks'],0)
        self.assertLessEqual(len(strings['probe'].bytecode),65535)
        self.assertTrue(all(len(s.bytecode)<=65535 for s in subroutines))
        self.assertLessEqual(report['maximum_added_subroutine_depth'],2)


if __name__=='__main__':unittest.main()
