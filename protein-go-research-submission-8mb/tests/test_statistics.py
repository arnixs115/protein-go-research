import importlib.util
from pathlib import Path
import unittest

import numpy as np
from scipy import special, stats

spec = importlib.util.spec_from_file_location('analysis', Path(__file__).resolve().parents[1] / 'scripts/04_analyze_statistics.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class StatisticsTests(unittest.TestCase):
    def test_bootstrap_reranks_tied_values_in_each_paired_sample(self):
        x = np.array([1, 1, 2, 3, 3, 4, 5, 8])
        ys = np.column_stack(([0, 0, 2, 1, 2, 2, 5, 4], [3, 2, 2, 0, 1, 1, 2, 0]))
        boot = analysis.paired_bootstrap(x, ys, 32, 12345, 'test')
        indices = np.random.default_rng(12345).integers(0, len(x), size=(32, len(x)))
        scalar = np.array([[stats.spearmanr(x[idx], ys[idx, j]).statistic for j in range(2)] for idx in indices])
        np.testing.assert_allclose(boot, scalar, atol=2e-15)
        np.testing.assert_array_equal(boot, analysis.paired_bootstrap(x, ys, 32, 12345, 'test_repeat'))

    def test_log_p_matches_independent_beta_identity_beyond_float_range(self):
        for rho, n in ((.02, 1000), (.27, 20431), (.6, 1000)):
            a, z = (n - 2) / 2, 1 - rho ** 2
            beta = special.betainc(a, .5, z)
            if beta > 0:
                independent = np.log(beta)
            else:
                # Positive-term hypergeometric series avoids hyp2f1's NaN for large a.
                term = total = 1.0
                for k in range(1, 10000):
                    term *= ((a + k - 1) * (k - .5) / ((a + k) * k)) * z
                    total += term
                    if term < 1e-16 * total:
                        break
                else:
                    self.fail('Independent beta series failed to converge')
                independent = a * np.log(z) - np.log(a) - special.betaln(a, .5) + np.log(total)
            self.assertAlmostEqual(analysis.log_two_sided_t_p(rho, n), independent, places=8)


if __name__ == '__main__':
    unittest.main()
