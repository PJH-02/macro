import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = REPO_ROOT / 'notebooks' / 'timefolio_contest_order.ipynb'
LATEST_MANIFEST_PATH = REPO_ROOT / 'src' / 'data' / 'snapshots' / 'latest.json'
LATEST_MANIFEST = json.loads(LATEST_MANIFEST_PATH.read_text(encoding='utf-8'))
LATEST_RUN_ID = LATEST_MANIFEST['run_id']
EXPECTED_SNAPSHOT = (
    REPO_ROOT
    / 'src'
    / 'data'
    / 'snapshots'
    / LATEST_RUN_ID
    / Path(LATEST_MANIFEST['screened_stocks_by_score_json']).name
)
PYPROJECT_CONTENT = (
    '[build-system]\n'
    'requires = ["setuptools"]\n'
    'build-backend = "setuptools.build_meta"\n'
)


def load_notebook() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(NOTEBOOK_PATH.read_text(encoding='utf-8')))


def load_setup_namespace() -> dict[str, Any]:
    notebook = load_notebook()
    namespace: dict[str, Any] = {}
    exec(''.join(notebook['cells'][2]['source']), namespace)
    return namespace


class TimefolioContestOrderNotebookTests(unittest.TestCase):
    def test_notebook_json_is_valid_and_uses_latest_manifest(self) -> None:
        notebook = load_notebook()
        self.assertEqual(notebook['nbformat'], 4)
        self.assertGreaterEqual(len(notebook['cells']), 4)

        intro = ''.join(notebook['cells'][0]['source'])
        setup_code = ''.join(notebook['cells'][2]['source'])

        self.assertIn('src/data/snapshots/latest.json', intro)
        self.assertIn('latest.json', setup_code)
        self.assertNotIn('/home/runner/work', setup_code)
        self.assertNotIn(LATEST_RUN_ID, setup_code)

    def test_repo_manifest_resolves_local_snapshot(self) -> None:
        namespace = load_setup_namespace()
        snapshot_path, manifest_path, manifest = namespace['load_latest_snapshot_path'](
            repo_root=REPO_ROOT
        )

        self.assertEqual(manifest_path, LATEST_MANIFEST_PATH)
        self.assertEqual(snapshot_path, EXPECTED_SNAPSHOT)
        self.assertTrue(snapshot_path.exists())
        self.assertEqual(Path(manifest['screened_stocks_by_score_json']).name, snapshot_path.name)
        self.assertFalse(str(snapshot_path).startswith('/home/runner/work'))

        screened_stocks = json.loads(snapshot_path.read_text(encoding='utf-8'))
        self.assertIsInstance(screened_stocks, list)
        self.assertGreater(len(screened_stocks), 0)

    def test_ci_absolute_manifest_path_falls_back_to_local_snapshot(self) -> None:
        namespace = load_setup_namespace()
        run_id = 'example-run'

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_repo = Path(tmpdir)
            (temp_repo / 'pyproject.toml').write_text(PYPROJECT_CONTENT, encoding='utf-8')
            snapshot_dir = temp_repo / 'src' / 'data' / 'snapshots' / run_id
            snapshot_dir.mkdir(parents=True)
            local_snapshot = snapshot_dir / 'screened_stocks_by_score.json'
            local_snapshot.write_text('[]\n', encoding='utf-8')

            latest_manifest = temp_repo / 'src' / 'data' / 'snapshots' / 'latest.json'
            latest_manifest.write_text(
                json.dumps(
                    {
                        'run_id': run_id,
                        'screened_stocks_by_score_json': (
                            '/home/runner/work/macro/macro/src/data/snapshots/'
                            f'{run_id}/screened_stocks_by_score.json'
                        ),
                    }
                ),
                encoding='utf-8',
            )

            snapshot_path, manifest_path, manifest = namespace['load_latest_snapshot_path'](
                repo_root=temp_repo
            )

        self.assertEqual(manifest_path, latest_manifest)
        self.assertEqual(snapshot_path, local_snapshot.resolve())
        self.assertEqual(manifest['run_id'], run_id)


if __name__ == '__main__':
    unittest.main()
