"""Optional local language identification; never changes datasets or training policy."""
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import uuid

if __package__:
    from . import decoder_datasets as datasets
    from .run_manifest import digest, file_digest
else:
    import decoder_datasets as datasets
    from run_manifest import digest, file_digest


def _recognize(texts):
    if platform.system() != 'Darwin':
        return None
    try:
        result = subprocess.run(['/usr/bin/osascript', '-l', 'JavaScript', str(Path(__file__).with_name('local_language.js'))],
                                input=json.dumps(texts, ensure_ascii=False), text=True, encoding='utf-8',
                                capture_output=True, timeout=10, check=True)
        if len(result.stdout) > 16384:
            return None
        candidates = json.loads(result.stdout)
        if not isinstance(candidates, list) or len(candidates) != len(texts):
            return None
        for row in candidates:
            if not isinstance(row, dict) or len(row) > 3:
                return None
            for language, confidence in row.items():
                if (not isinstance(language, str) or not re.fullmatch('[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', language)
                        or type(confidence) not in (float, int) or not math.isfinite(confidence)
                        or not 0 <= confidence <= 1):
                    return None
        return candidates
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def analyze(root, dataset_id, confirmed):
    if confirmed is not True:
        raise ValueError('Confirm local document language identification.')
    manifest = datasets.read(root, dataset_id)
    rows = [json.loads(line) for line in (Path(root)/'decoder-datasets'/dataset_id/'documents.jsonl').read_text(encoding='utf-8').splitlines()]
    eligible = [index for index, row in enumerate(rows) if sum(char.isalpha() for char in row['text']) >= 40]
    predictions = _recognize([rows[index]['text'] for index in eligible]) if eligible else []
    by_index = dict(zip(eligible, predictions)) if predictions is not None else {}
    records = []
    for index, row in enumerate(rows):
        candidates = sorted(by_index.get(index, {}).items(), key=lambda item: (-item[1], item[0]))
        confidence = candidates[0][1] if candidates else 0.0
        margin = confidence - (candidates[1][1] if len(candidates) > 1 else 0.0)
        identified = bool(candidates) and candidates[0][0] != 'und' and confidence >= .8 and margin >= .2
        reason = 'insufficient_alphabetic_text' if index not in eligible else 'provider_unavailable' if predictions is None else 'ambiguous_or_unrecognized'
        records.append({**{key: row[key] for key in ('name','source_sha256','group','split')},
                        'status': 'identified' if identified else 'unknown',
                        'language': candidates[0][0] if identified else 'und',
                        'confidence': round(confidence, 6),
                        'reason': 'confidence_and_margin_met' if identified else reason,
                        'candidates': [{'language': language, 'confidence': round(value, 6)} for language, value in candidates]})
    report = {'format':'almg-decoder-languages-v1','schema_version':1,'dataset_id':dataset_id,
              'dataset_manifest_sha256':digest(manifest),
              'method':{'provider':'apple_natural_language_optional','version':1,
                        'minimum_alphabetic_characters':40,'minimum_confidence':.8,'minimum_margin':.2,
                        'maximum_candidates':3,'granularity':'dominant_language_per_document',
                        'limitations':'Probabilistic dominant-language estimate; mixed, short or unsupported text may be unknown.'},
              'runtime':{'system':platform.system(),'macos_version':platform.mac_ver()[0],
                         'machine':platform.machine(),'provider_available':predictions is not None if eligible else None},
              'implementation_sha256':file_digest(Path(__file__)),
              'adapter_sha256':file_digest(Path(__file__).with_name('local_language.js')),
              'identified_records':sum(row['status']=='identified' for row in records),
              'unknown_records':sum(row['status']=='unknown' for row in records),'records':records}
    report['revision'] = digest(report)
    directory = Path(root)/'decoder-language-reports'/dataset_id
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory/(report['revision']+'.json')
    if destination.exists():
        if json.loads(destination.read_text(encoding='utf-8')) != report:
            raise ValueError('Saved language report integrity check failed.')
    else:
        temporary = directory/(uuid.uuid4().hex+'.tmp')
        try:
            temporary.write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return report


def list_reports(root, dataset_id):
    manifest = datasets.read(root, dataset_id)
    directory = Path(root)/'decoder-language-reports'/dataset_id
    result = []
    for path in sorted(directory.glob('*.json')) if directory.exists() else []:
        try:
            report = json.loads(path.read_text(encoding='utf-8'))
            if (report.get('format') != 'almg-decoder-languages-v1'
                    or type(report.get('schema_version')) is not int or report['schema_version'] != 1
                    or report.get('dataset_id') != dataset_id or report.get('dataset_manifest_sha256') != digest(manifest)
                    or report.get('revision') != path.stem
                    or report['revision'] != digest({key:value for key,value in report.items() if key!='revision'})):
                continue
            result.append(report)
        except (OSError,ValueError,TypeError,KeyError,AttributeError):
            continue
    return result[-20:]
