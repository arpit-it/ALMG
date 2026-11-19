"""Durable explicitly approved generated-text decoder trials, separate from jobs."""
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import re
import threading
import uuid

if __package__:
    from . import decoder_bundle, decoder_dataset_training, decoder_training, recipe_contracts, run_manifest, training_resources
else:
    import decoder_bundle, decoder_dataset_training, decoder_training, recipe_contracts, run_manifest, training_resources

_LOCK = threading.Lock()
_ACTIVE = set()
_CANCEL = {}
_READINESS = {}


class ReadinessPaused(ValueError):
    """A guarded trial needs renewed explicit approval after readiness changes."""


def require_readiness(probe):
    try:
        state = probe() if callable(probe) else None
        idle = state.get('idle_seconds') if isinstance(state, dict) else None
        valid = (isinstance(state, dict) and state.get('ready') is True
                 and state.get('ac_power') is True and type(idle) in (int, float)
                 and 600 <= idle < 1e12)
    except Exception:
        valid = False
    if not valid:
        raise ReadinessPaused('Idle/AC readiness is not confirmed. Require AC power and 600 idle seconds; review and approve again when ready.')


def specification(dataset=None):
    spec = {'recipe': 'decoder_from_scratch', 'recipe_version': 1, 'approach': 'from_scratch',
            'scope': 'generated_local_text_fixture', 'stage_version': 1,
            'recipe_contract': recipe_contracts.recipe_contract('decoder_from_scratch'),
            'resource_budget': {'version': 1, 'encoded_data_bytes': 128000},
            'components': {name: run_manifest.file_digest(Path(__file__).with_name(name)) for name in
                           ('decoder_trials.py', 'decoder_training.py', 'decoder_recipe.py', 'decoder_tokenizer.py',
                            'decoder_checkpoint.py', 'decoder_dataset_training.py', 'decoder_bundle.py', 'training_resources.py')}}
    if dataset is not None:
        spec.update(scope='reviewed_local_text_trial', dataset_id=dataset['id'],
                    dataset_manifest_sha256=run_manifest.digest(dataset))
    return spec


def propose(root, goal, planner, planner_identity=None, dataset=None):
    if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 3000:
        raise ValueError('Describe the trial goal in 1 to 3000 characters.')
    if dataset is not None:
        dataset = decoder_dataset_training.preflight(root, dataset)[0]
    spec = specification(dataset) if dataset is not None else specification()
    summary = None if dataset is None else {
        key: dataset[key] for key in ('id', 'unique_documents', 'splits', 'tokenizer', 'findings')}
    catalog = recipe_contracts.planning_catalog('decoder_trial')
    available = {contract['id']: contract for contract in catalog}
    if spec['recipe'] not in available:
        raise ValueError('The registered decoder trial recipe is unavailable.')
    result = planner(
        'Recommend one approach: from_scratch, fine_tuning, distillation, or retrieval. '
        'Only a tiny from_scratch local text trial is executable here, using the selected reviewed dataset when supplied. '
        'The selected dataset summary contains preparation evidence, not document contents. Pretrained adaptation and retrieval execution are unavailable. '
        'Return recipe (a registered ID), approach and a short reason. Do not execute tools or claim that a trial satisfies a general user-model goal.',
        {'goal': goal.strip(), 'available_trial': spec, 'dataset_summary': summary, 'registered_recipes': catalog})
    if not isinstance(result, dict):
        raise ValueError('The planner returned an invalid proposal.')
    selected = result.get('recipe')
    if not isinstance(selected, str) or selected not in available or selected != spec['recipe']:
        raise ValueError('The planner selected an unavailable decoder trial recipe.')
    contract = available[selected]
    approach, reason = result.get('approach'), result.get('reason')
    if approach not in ('from_scratch', 'fine_tuning', 'distillation', 'retrieval'):
        raise ValueError('The planner returned an unsupported approach.')
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 600:
        raise ValueError('The planner must provide a short explanation.')
    if dataset is not None:
        decoder_dataset_training.preflight(root, dataset)
    if spec != (specification(dataset) if dataset is not None else specification()):
        raise ValueError('Available trial capabilities changed while planning. Request a fresh proposal.')
    proposal = {'schema_version': 1, 'id': uuid.uuid4().hex, 'goal': goal.strip(),
                'approach': approach, 'reason': reason.strip(),
                'recipe': selected, 'recipe_contract': contract,
                'scope': spec.get('scope', 'generated_local_text_fixture'),
                'executable': approach in contract['planning']['approaches'] and spec['scope'] in contract['planning']['scopes'],
                'dataset_summary': summary,
                'specification_revision': run_manifest.digest(spec),
                'planner': planner_identity() if planner_identity is not None else {'provider': 'unspecified'}}
    proposal['revision'] = run_manifest.digest(proposal)
    directory = Path(root) / 'decoder-trial-proposals'
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / (proposal['id'] + '.tmp')
    temporary.write_text(json.dumps(proposal, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(directory / (proposal['id'] + '.json'))
    return proposal


def approved_proposal(root, proposal_id, revision, spec):
    folder(root, proposal_id)  # Validate the identifier before constructing a path.
    try:
        proposal = json.loads((Path(root) / 'decoder-trial-proposals' / (proposal_id + '.json')).read_text(encoding='utf-8'))
        payload = {key: value for key, value in proposal.items() if key != 'revision'}
        if (type(proposal.get('schema_version')) is not int or proposal['schema_version'] != 1
                or proposal.get('id') != proposal_id or proposal.get('revision') != revision
                or proposal['revision'] != run_manifest.digest(payload)
                or proposal.get('specification_revision') != run_manifest.digest(spec)):
            raise ValueError('The proposal changed. Request and review a fresh proposal before approving.')
        if proposal.get('approach') != 'from_scratch' or proposal.get('executable') is not True:
            raise ValueError('This approach cannot execute in the local decoder trial workflow.')
        return proposal
    except (OSError, TypeError, AttributeError) as error:
        raise ValueError('The trial proposal is unavailable. Request and review a new proposal.') from error


def approval_revision(record):
    if record.get('scheduling') is not None:
        return run_manifest.digest({key: record.get(key) for key in ('specification', 'proposal', 'scheduling')})
    if record.get('proposal') is None:
        return run_manifest.digest(record['specification'])
    return run_manifest.digest({'specification': record['specification'], 'proposal': record['proposal']})


def folder(root, trial_id):
    if not isinstance(trial_id, str) or not re.fullmatch('[a-f0-9]{32}', trial_id):
        raise ValueError('Invalid decoder trial ID.')
    return Path(root) / 'decoder-trials' / trial_id


def write(root, record):
    path = folder(root, record['id'])
    path.mkdir(parents=True, exist_ok=True)
    temporary = path / 'record.tmp'
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temporary.replace(path / 'record.json')


def read(root, trial_id):
    try:
        record = json.loads((folder(root, trial_id) / 'record.json').read_text(encoding='utf-8'))
        if (type(record.get('schema_version')) is not int or record['schema_version'] != 1 or record.get('id') != trial_id
                or not isinstance(record.get('created_at'), str)
                or record.get('status') not in ('waiting_idle', 'queued', 'running', 'interrupted', 'complete')):
            raise ValueError('Unsupported decoder trial record.')
        return record
    except (OSError, TypeError, AttributeError) as error:
        raise ValueError('Decoder trial record is unavailable or unreadable.') from error


def list_trials(root, limit=20):
    directory = Path(root) / 'decoder-trials'
    records = []
    if directory.exists():
        for path in directory.iterdir():
            if re.fullmatch('[a-f0-9]{32}', path.name):
                try:
                    records.append(read(root, path.name))
                except ValueError:
                    continue
    return sorted(records, key=lambda record: record.get('created_at', ''), reverse=True)[:limit]


def infer_bundle(bundle_path, prompt, max_new_tokens):
    """Bounded CPU inference shared by trained trials and private imports."""
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4096:
        raise ValueError('Provide a prompt of 1 to 4096 characters from the saved vocabulary.')
    if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 32:
        raise ValueError('Generate between 1 and 32 new tokens.')
    model, tokenizer, manifest = decoder_bundle.load(bundle_path)
    tokens = tokenizer.encode(prompt.strip())
    if len(tokens) > model.config['context_length']:
        raise ValueError('The prompt exceeds the saved decoder context length.')
    import numpy as np
    generated = []
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            for _ in range(max_new_tokens):
                scores = model.logits([tokens[-model.config['context_length']:]])[0, -1]
                if not np.isfinite(scores).all():
                    raise ValueError('The private decoder produced invalid inference scores.')
                token = int(np.argmax(scores))
                tokens.append(token)
                generated.append(token)
    except FloatingPointError as error:
        raise ValueError('The private decoder produced invalid inference scores.') from error
    result = {'schema_version': 1, 'id': uuid.uuid4().hex,
              'created_at': datetime.now(timezone.utc).isoformat(),
              'prompt': prompt.strip(), 'completion': tokenizer.decode(generated),
              'text': tokenizer.decode(tokens), 'generated_token_ids': generated,
              'bundle_manifest_sha256': run_manifest.digest(manifest),
              'inference': {'version': 1, 'algorithm': 'greedy', 'runtime': 'numpy_cpu',
                            'max_new_tokens': max_new_tokens, 'context_policy': 'sliding_window',
                            'source_sha256': run_manifest.file_digest(Path(__file__))},
              'scope': 'Private local trial preview; no model release.'}
    return result


def preview(root, trial_id, confirmed, prompt, max_new_tokens=12, persist=True):
    if confirmed is not True:
        raise ValueError('Confirm local inference on this private decoder trial.')
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4096:
        raise ValueError('Provide a prompt of 1 to 4096 characters from the saved vocabulary.')
    if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 32:
        raise ValueError('Generate between 1 and 32 new tokens.')
    with _LOCK:
        record = read(root, trial_id)
        if record['status'] != 'complete':
            raise ValueError('Complete the private decoder trial before previewing it.')
    result = infer_bundle(folder(root, trial_id)/'artifacts/bundle', prompt, max_new_tokens)
    result['trial_id'] = trial_id
    if persist:
        with _LOCK:
            saved = read(root, trial_id)
            saved['previews'] = [*saved.get('previews', [])[-19:], result]
            write(root, saved)
    return result


def evaluate(root, trial_id, confirmed, persist=True):
    """Recompute a versioned private evaluation from verified held-out documents."""
    if confirmed is not True:
        raise ValueError('Confirm re-evaluation of this saved private decoder.')
    with _LOCK:
        saved = read(root, trial_id)
        if saved['status'] != 'complete' or not isinstance(saved.get('dataset'), dict):
            raise ValueError('Complete a reviewed-local-dataset trial before re-evaluation.')
        reviewed = saved['dataset']
    dataset, prepared_tokenizer, _, batches = decoder_dataset_training.preflight(root, reviewed)
    model, tokenizer, bundle = decoder_bundle.load(folder(root, trial_id) / 'artifacts' / 'bundle')
    training = bundle['training']
    if (training.get('scope') != 'reviewed_local_text_trial'
            or training.get('dataset_id') != dataset['id']
            or training.get('dataset_sha256') != dataset['dataset_sha256']
            or training.get('review_sha256') != run_manifest.digest(dataset)
            or tokenizer.fingerprint() != prepared_tokenizer.fingerprint()
            or bundle['stages'].get('pretraining_local') != 1):
        raise ValueError('The saved bundle is not bound to this reviewed dataset and tokenizer.')
    import numpy as np
    initial = training.get('evaluation', {}).get('initial_train_loss')
    if type(initial) not in (float, int) or not np.isfinite(initial) or initial <= 0:
        raise ValueError('The bundle lacks a valid initial training-loss reference.')
    metrics = {}
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            for part in ('train', 'validation', 'test'):
                correct = count = 0
                loss_sum = 0.0
                for window in batches[part]:
                    scores = model.logits([window[:-1]])[0].astype(np.float64)
                    if not np.isfinite(scores).all():
                        raise ValueError('The saved decoder produced invalid evaluation scores.')
                    targets = np.array(window[1:])
                    maximum = np.max(scores, axis=-1)
                    losses = maximum + np.log(np.sum(np.exp(scores-maximum[:, None]), axis=-1)) - scores[np.arange(len(targets)), targets]
                    correct += int(np.sum(np.argmax(scores, axis=-1) == targets))
                    count += len(targets)
                    loss_sum += float(np.sum(losses))
                loss = loss_sum / count
                if not np.isfinite(loss):
                    raise ValueError('The saved decoder produced invalid evaluation loss.')
                metrics[part] = {'next_token_accuracy': correct/count, 'cross_entropy': loss,
                                 'evaluated_tokens': count, 'windows': len(batches[part])}
    except FloatingPointError as error:
        raise ValueError('The saved decoder produced invalid evaluation scores.') from error
    passed = (min(metrics[part]['next_token_accuracy'] for part in ('validation', 'test')) >= .8
              and metrics['train']['cross_entropy'] < initial)
    result = {'schema_version': 1, 'evaluation_version': 1, 'id': uuid.uuid4().hex,
              'created_at': datetime.now(timezone.utc).isoformat(), 'trial_id': trial_id,
              'bundle_manifest_sha256': run_manifest.digest(bundle),
              'dataset_manifest_sha256': run_manifest.digest(dataset),
              'dataset_sha256': dataset['dataset_sha256'], 'tokenizer_sha256': tokenizer.fingerprint(),
              'runtime': {'device': 'CPU', 'numpy': np.__version__},
              'implementation_sha256': run_manifest.file_digest(Path(__file__)),
              'target_next_token_accuracy': .8, 'initial_train_loss_reference': initial,
              'metrics': metrics, 'passed': bool(passed),
              'scope': 'Private held-out re-evaluation; no model release.'}
    if persist:
        with _LOCK:
            record = read(root, trial_id)
            record['evaluations'] = [*record.get('evaluations', [])[-19:], result]
            write(root, record)
    return result


def export_material(root, trial_id):
    """Build a review of exact immutable files after fresh independent evaluation."""
    fresh = evaluate(root, trial_id, True, persist=False)
    if fresh['passed'] is not True:
        raise ValueError('The saved decoder does not meet its evaluation target; private export is unavailable.')
    with _LOCK:
        record = read(root, trial_id)
        evaluations, previews = record.get('evaluations', []), record.get('previews', [])
        if not evaluations or not previews:
            raise ValueError('Save a passing independent evaluation and a private preview before export.')
        evaluation, preview_record = evaluations[-1], previews[-1]
    if (evaluation.get('passed') is not True or type(evaluation.get('evaluation_version')) is not int or evaluation['evaluation_version'] != 1
            or evaluation.get('target_next_token_accuracy') != fresh['target_next_token_accuracy']
            or run_manifest.digest(evaluation.get('metrics')) != run_manifest.digest(fresh['metrics'])
            or any(evaluation.get(key) != fresh[key] for key in (
                'bundle_manifest_sha256', 'dataset_manifest_sha256', 'dataset_sha256', 'tokenizer_sha256'))
            or preview_record.get('bundle_manifest_sha256') != fresh['bundle_manifest_sha256']
            or preview_record.get('trial_id') != trial_id or not preview_record.get('generated_token_ids')):
        raise ValueError('Evaluation or preview no longer matches this bundle. Re-evaluate and preview again.')
    inference = preview_record.get('inference')
    if (not isinstance(inference, dict) or type(inference.get('version')) is not int or inference['version'] != 1):
        raise ValueError('A versioned private preview is required before export.')
    repeated_preview = preview(root, trial_id, True, preview_record.get('prompt'), inference.get('max_new_tokens'), persist=False)
    if any(preview_record.get(key) != repeated_preview[key] for key in ('generated_token_ids', 'completion', 'text', 'bundle_manifest_sha256')):
        raise ValueError('The saved preview does not reproduce against this bundle. Preview again.')
    bundle_path = folder(root, trial_id) / 'artifacts' / 'bundle'
    contents = {f'bundle/{name}': (bundle_path/name).read_bytes()
                for name in ('decoder.json', 'tokenizer.json', 'manifest.json')}
    manifest = json.loads(contents['bundle/manifest.json'])
    if (run_manifest.digest(manifest) != fresh['bundle_manifest_sha256']
            or any(hashlib.sha256(contents['bundle/'+name]).hexdigest() != expected
                   for name, expected in manifest['files'].items())):
        raise ValueError('Bundle files changed while reviewing export.')
    review = {'schema_version': 1, 'format': 'almg-private-decoder-export-v1', 'trial_id': trial_id,
              'scope': 'Private experimental bundle only; no model release or dataset documents.',
              'bundle_manifest_sha256': fresh['bundle_manifest_sha256'],
              'dataset_manifest_sha256': fresh['dataset_manifest_sha256'],
              'evaluation_revision': run_manifest.digest(evaluation), 'preview_revision': run_manifest.digest(preview_record),
              'files': {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
              'receipts': ['evaluation', 'preview'], 'evaluation_verified': True,
              'implementation_sha256': run_manifest.file_digest(Path(__file__))}
    review['revision'] = run_manifest.digest(review)
    return review, contents, evaluation, preview_record


def export_review(root, trial_id):
    return export_material(root, trial_id)[0]


def export_private(root, trial_id, confirmed, revision):
    if confirmed is not True:
        raise ValueError('Confirm saving this private decoder export.')
    review, contents, evaluation, preview_record = export_material(root, trial_id)
    if revision != review['revision']:
        raise ValueError('The export review changed. Review the current bundle and receipts again.')
    import base64
    import hashlib
    import io
    from tempfile import TemporaryDirectory
    import zipfile
    export_id = uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).isoformat()
    manifest = {'format': review['format'], 'schema_version': 1, 'export_id': export_id,
                'created_at': timestamp, 'approved_review': review,
                'evaluation': evaluation, 'preview': preview_record}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
        archive.writestr('export-manifest.json', json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2))
    data = output.getvalue()
    receipt = {'id': export_id, 'format': review['format'], 'created_at': timestamp,
               'review_revision': revision, 'archive_sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    directory = Path(root)/'decoder-exports'
    directory.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.export-', dir=directory) as temporary:
        staged = Path(temporary)/export_id
        staged.mkdir()
        (staged/'bundle.zip').write_bytes(data)
        (staged/'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        staged.rename(directory/export_id)
    with _LOCK:
        record = read(root, trial_id)
        record['exports'] = [*record.get('exports', [])[-19:], receipt]
        write(root, record)
    return {**receipt, 'file_name': f'decoder-private-{trial_id[:8]}.zip', 'data': base64.b64encode(data).decode('ascii')}


def import_folder(root, import_id):
    folder(root, import_id)  # Validate identifiers without trusting archive paths.
    return Path(root)/'decoder-imports'/import_id


def read_import(root, import_id, verify=True):
    try:
        path = import_folder(root, import_id)
        record = json.loads((path/'import.json').read_text(encoding='utf-8'))
        if (type(record.get('schema_version')) is not int or record['schema_version'] != 1
                or record.get('format') != 'almg-private-decoder-import-v1' or record.get('id') != import_id
                or record.get('scope') != 'private_cpu_preview_only'
                or record.get('evaluation_status') != 'not_re_evaluated_dataset_excluded'
                or not isinstance(record.get('created_at'), str) or not isinstance(record.get('source_name'), str)):
            raise ValueError('Unsupported private decoder import.')
        if verify:
            _, tokenizer, manifest = decoder_bundle.load(path/'bundle')
            if (run_manifest.digest(manifest) != record['bundle_manifest_sha256']
                    or tokenizer.artifact()['format'] != record['tokenizer_format']
                    or record.get('config') != manifest['config']
                    or run_manifest.file_digest(path/'export-manifest.json') != record['provenance_sha256']):
                raise ValueError('Imported decoder integrity changed.')
        return record
    except (OSError, KeyError, TypeError, AttributeError) as error:
        raise ValueError('Private imported decoder is unavailable or incomplete.') from error


def list_imports(root):
    directory = Path(root)/'decoder-imports'
    records = []
    for path in directory.iterdir() if directory.exists() else []:
        if re.fullmatch('[a-f0-9]{32}', path.name):
            try:
                records.append(read_import(root, path.name, verify=False))
            except ValueError:
                continue
    return sorted(records, key=lambda item:item.get('created_at', ''), reverse=True)[:20]


def library_imports(root):
    """Expose private inventory separately from released/candidate training models."""
    rows = []
    for record in list_imports(root):
        missing = []
        try:
            read_import(root, record['id'])
        except ValueError:
            missing = ['Private bundle integrity check failed; import the original archive again.']
        try:
            created = datetime.fromisoformat(record['created_at']).timestamp()
        except ValueError:
            created = None
        rows.append({'id':record['id'], 'name':record['source_name'], 'project':'Private imports',
                     'recipe':'decoder_from_scratch', 'kind':'private_decoder_import', 'status':'private_import',
                     'scope':'private_cpu_preview_only', 'evaluation_status':'not_re_evaluated_dataset_excluded',
                     'missing_files':missing, 'created_at':created})
    return rows


def import_private(root, confirmed, source_name, encoded):
    if confirmed is not True:
        raise ValueError('Confirm importing this private decoder for CPU preview.')
    if not isinstance(source_name, str) or not 1 <= len(source_name) <= 255:
        raise ValueError('Provide a short archive name.')
    if not isinstance(encoded, str) or len(encoded) > 12*1024*1024:
        raise ValueError('Private decoder archives must fit 8 MiB.')
    import base64
    import io
    import stat
    from tempfile import TemporaryDirectory
    import zipfile
    try:
        data = base64.b64decode(encoded, validate=True)
        if not 0 < len(data) <= 8*1024*1024:
            raise ValueError('Private decoder archives must fit 8 MiB.')
        limits = {'bundle/decoder.json':4*1024*1024, 'bundle/tokenizer.json':128*1024,
                  'bundle/manifest.json':256*1024, 'export-manifest.json':512*1024}
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) != len(limits) or {info.filename for info in infos} != set(limits):
                raise ValueError('Import requires exactly the versioned private decoder ZIP members.')
            contents = {}
            for info in infos:
                if (info.flag_bits & 1 or info.file_size > limits[info.filename]
                        or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                        or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)):
                    raise ValueError('Private decoder archive contains unsupported or oversized entries.')
                with archive.open(info) as stream:
                    content = stream.read(limits[info.filename]+1)
                if len(content) != info.file_size or len(content) > limits[info.filename]:
                    raise ValueError('Private decoder archive entry size mismatch.')
                contents[info.filename] = content
        provenance = json.loads(contents['export-manifest.json'])
        review = provenance['approved_review']
        if (provenance.get('format') != 'almg-private-decoder-export-v1'
                or type(provenance.get('schema_version')) is not int or provenance['schema_version'] != 1
                or review.get('revision') != run_manifest.digest({k:v for k,v in review.items() if k!='revision'})
                or review.get('files') != {name:hashlib.sha256(content).hexdigest() for name,content in contents.items() if name!='export-manifest.json'}
                or review.get('evaluation_revision') != run_manifest.digest(provenance['evaluation'])
                or review.get('preview_revision') != run_manifest.digest(provenance['preview'])):
            raise ValueError('Private decoder archive provenance or file hashes do not match.')
        directory = Path(root)/'decoder-imports'
        directory.mkdir(parents=True, exist_ok=True)
        import_id = uuid.uuid4().hex
        with TemporaryDirectory(prefix='.import-', dir=directory) as temporary:
            staged = Path(temporary)/import_id
            (staged/'bundle').mkdir(parents=True)
            for name,content in contents.items():
                (staged/name).write_bytes(content)
            _, tokenizer, manifest = decoder_bundle.load(staged/'bundle')
            if run_manifest.digest(manifest) != review['bundle_manifest_sha256']:
                raise ValueError('Imported bundle revision does not match its export review.')
            record = {'schema_version':1, 'format':'almg-private-decoder-import-v1', 'id':import_id,
                      'created_at':datetime.now(timezone.utc).isoformat(), 'source_name':source_name,
                      'archive_sha256':hashlib.sha256(data).hexdigest(), 'bundle_manifest_sha256':run_manifest.digest(manifest),
                      'provenance_sha256':hashlib.sha256(contents['export-manifest.json']).hexdigest(),
                      'tokenizer_format':tokenizer.artifact()['format'], 'config':manifest['config'],
                      'scope':'private_cpu_preview_only', 'evaluation_status':'not_re_evaluated_dataset_excluded'}
            (staged/'import.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
            staged.rename(directory/import_id)
        return record
    except (OSError, KeyError, TypeError, AttributeError, zipfile.BadZipFile, RuntimeError) as error:
        raise ValueError('The private decoder archive is invalid or incomplete.') from error


def preview_import(root, import_id, confirmed, prompt, max_new_tokens=12):
    if confirmed is not True:
        raise ValueError('Confirm CPU preview of this imported private decoder.')
    read_import(root, import_id)
    result = infer_bundle(import_folder(root, import_id)/'bundle', prompt, max_new_tokens)
    result['import_id'] = import_id
    result['scope'] = 'Imported private CPU preview only; no training or release.'
    with _LOCK:
        saved = read_import(root, import_id, verify=False)
        saved['previews'] = [*saved.get('previews', [])[-19:], result]
        path = import_folder(root, import_id)/'import.json'
        pending = path.with_suffix('.tmp')
        pending.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
        pending.replace(path)
    return result


def recover(root):
    """A restarted backend never resumes work without renewed approval."""
    for record in list_trials(root, limit=None):
        with _LOCK:
            if (str(Path(root)), record['id']) not in _ACTIVE and record.get('status') in ('waiting_idle', 'queued', 'running'):
                record.update(status='interrupted', error='Backend stopped. Review the saved trial and approve resume.')
                write(root, record)


def cancel(root, trial_id, confirmed):
    if confirmed is not True:
        raise ValueError('Confirm cancellation of this saved trial.')
    key = (str(Path(root)), trial_id)
    with _LOCK:
        record = read(root, trial_id)
        if record['status'] not in ('waiting_idle', 'queued', 'running') or key not in _CANCEL:
            raise ValueError('Only an active saved trial can be cancelled.')
        _CANCEL[key].set()
        record.update(cancel_requested=True, error='Cancellation requested; waiting for the next training boundary.')
        write(root, record)
    return record


def record_resources(root, record, phase):
    """Use the full bounded import budget, also for smaller generated fixtures."""
    evidence = training_resources.check_size(record['specification']['resource_budget']['encoded_data_bytes'], Path(root))
    record['resource_checks'] = [*record.get('resource_checks', [])[-19:], {
        'phase': phase, 'checked_at': datetime.now(timezone.utc).isoformat(), **evidence}]


def monitor_resources(root, trial_id, spec):
    """Probe at a cooperative boundary and merge evidence without losing cancel state."""
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        evidence = training_resources.check_size(spec['resource_budget']['encoded_data_bytes'], Path(root))
    except training_resources.ResourceUnavailable as error:
        with _LOCK:
            saved = read(root, trial_id)
            monitor = saved.setdefault('resource_monitor', {'version': 1, 'successful_boundaries': 0})
            monitor['last_failure'] = {'checked_at': timestamp, 'error': str(error)}
            write(root, saved)
        raise
    with _LOCK:
        saved = read(root, trial_id)
        monitor = saved.setdefault('resource_monitor', {'version': 1, 'successful_boundaries': 0})
        monitor['successful_boundaries'] += 1
        monitor['latest'] = {'checked_at': timestamp, **evidence}
        write(root, saved)


def execute(root, trial_id):
    key = (str(Path(root)), trial_id)
    try:
        with _LOCK:
            record = read(root, trial_id)
            stop_event = _CANCEL[key]
            dataset = record.get('dataset')
            if dataset is not None:
                decoder_dataset_training.preflight(root, dataset)
            current_spec = specification(dataset) if dataset is not None else specification()
            if (record.get('specification') != current_spec
                    or record.get('approval', {}).get('revision') != approval_revision(record)):
                raise ValueError('Saved decoder trial approval no longer matches this implementation. Approve a new trial.')
            if stop_event.is_set():
                raise decoder_training.Cancelled('Cancelled before training. Approve resume to continue.')
            record_resources(root, record, 'execution')
            record.update(status='running', error=None, artifact_directory=str(folder(root, trial_id) / 'artifacts'))
            write(root, record)
        def stop():
            if stop_event.is_set():
                return True
            if record.get('scheduling', {}).get('require_idle_ac') is True:
                require_readiness(_READINESS.get(key))
            monitor_resources(root, trial_id, current_spec)
            return stop_event.is_set()

        if dataset is None:
            result = decoder_training.run(recipe_contracts.initialize_recipe,
                                          work_directory=folder(root, trial_id) / 'artifacts', stop=stop)
        else:
            result = decoder_dataset_training.run(recipe_contracts.initialize_recipe, root, dataset,
                work_directory=folder(root, trial_id) / 'artifacts', stop=stop)
        with _LOCK:
            record = read(root, trial_id)
            if stop_event.is_set():
                record.update(status='interrupted', interruption_reason='user_cancelled',
                              error='Cancelled; any completed artifacts are preserved. Approve a new trial if a complete bundle exists.')
            else:
                record.update(status='complete', result=result, artifact_directory=str(folder(root, trial_id) / 'artifacts'))
            write(root, record)
    except Exception as error:
        with _LOCK:
            record = read(root, trial_id)
            record.update(status='interrupted', error=str(error))
            if isinstance(error, decoder_training.Cancelled):
                record['interruption_reason'] = 'user_cancelled'
            elif isinstance(error, ReadinessPaused):
                record['interruption_reason'] = 'readiness_changed'
            elif isinstance(error, training_resources.ResourceUnavailable):
                record['interruption_reason'] = 'resources_unavailable'
            write(root, record)
    finally:
        with _LOCK:
            _ACTIVE.discard(key)
            _CANCEL.pop(key, None)
            _READINESS.pop(key, None)


def wait_and_submit(root, trial_id, submit):
    """Wait outside the training worker; approval does not need an already-idle UI."""
    key = (str(Path(root)), trial_id)
    dispatched = False
    try:
        event = _CANCEL[key]
        while True:
            if event.is_set():
                raise decoder_training.Cancelled('Cancelled while waiting for idle time and AC power.')
            try:
                require_readiness(_READINESS.get(key))
            except ReadinessPaused:
                if event.wait(2):
                    raise decoder_training.Cancelled('Cancelled while waiting for idle time and AC power.')
                continue
            with _LOCK:
                record = read(root, trial_id)
                record.update(status='queued', error=None)
                write(root, record)
            submit(execute, root, trial_id)
            dispatched = True
            return
    except Exception as error:
        with _LOCK:
            record = read(root, trial_id)
            record.update(status='interrupted', error=str(error),
                          interruption_reason='user_cancelled' if isinstance(error, decoder_training.Cancelled) else 'worker_unavailable')
            write(root, record)
    finally:
        if not dispatched:
            with _LOCK:
                _ACTIVE.discard(key)
                _CANCEL.pop(key, None)
                _READINESS.pop(key, None)


def start(root, confirmed, submit, trial_id=None, proposal_id=None, proposal_revision=None, dataset=None, require_idle_ac=None, readiness=None):
    if confirmed is not True:
        raise ValueError('Approve the generated-text decoder trial before starting it.')
    if require_idle_ac is not None and type(require_idle_ac) is not bool:
        raise ValueError('Idle/AC guard must be true or false.')
    spec = specification()
    if dataset is not None and trial_id is not None:
        raise ValueError('Review local-dataset training separately; a generated-text proposal or existing trial cannot change data scope.')
    if dataset is not None:
        dataset = decoder_dataset_training.preflight(root, dataset)[0]
        spec = specification(dataset)
    with _LOCK:
        if trial_id is None:
            trial_id = uuid.uuid4().hex
            record = {'schema_version': 1, 'id': trial_id, 'created_at': datetime.now(timezone.utc).isoformat()}
            if proposal_id is not None:
                record['proposal'] = approved_proposal(root, proposal_id, proposal_revision, spec)
            if dataset is not None:
                record['dataset'] = dataset
        else:
            record = read(root, trial_id)
            if record.get('status') != 'interrupted' or (str(Path(root)), trial_id) in _ACTIVE:
                raise ValueError('Only an interrupted decoder trial can be resumed.')
            if record.get('dataset') is not None:
                resumed_dataset = decoder_dataset_training.preflight(root, record['dataset'])[0]
                spec = specification(resumed_dataset)
            if record.get('specification') != spec:
                raise ValueError('Decoder trial implementation changed. Approve a new trial instead.')
            if (folder(root, trial_id) / 'artifacts' / 'bundle').exists():
                raise ValueError('A complete bundle already exists. Preserve it and approve a new trial instead.')
        guarded = record.get('scheduling', {}).get('require_idle_ac', False)
        if trial_id is not None and record.get('approval') is not None and require_idle_ac is not None and require_idle_ac != guarded:
            raise ValueError('The saved trial execution policy cannot change during resume.')
        if record.get('approval') is None and require_idle_ac is True:
            record['scheduling'] = {'require_idle_ac': True, 'required_idle_seconds': 600,
                                    'on_readiness_change': 'interrupt_and_require_approval'}
            guarded = True
        if guarded and not callable(readiness):
            raise ValueError('A local readiness probe is required for guarded training.')
        resource_record = {'specification': spec, 'resource_checks': list(record.get('resource_checks', []))}
        record_resources(root, resource_record, 'admission')
        record['resource_checks'] = resource_record['resource_checks']
        if record.get('approval') is not None:
            record.setdefault('previous_approvals', []).append(record['approval'])
        record.update(status='waiting_idle' if guarded else 'queued', error=None, cancel_requested=False, interruption_reason=None, specification=spec,
                      approval={'id': uuid.uuid4().hex, 'confirmed_at': datetime.now(timezone.utc).isoformat(),
                                'revision': run_manifest.digest(spec)})
        record['approval']['revision'] = approval_revision(record)
        write(root, record)
        _ACTIVE.add((str(Path(root)), trial_id))
        _CANCEL[(str(Path(root)), trial_id)] = threading.Event()
        if guarded:
            _READINESS[(str(Path(root)), trial_id)] = readiness
    try:
        if guarded:
            threading.Thread(target=wait_and_submit, args=(root, trial_id, submit), daemon=True).start()
        else:
            submit(execute, root, trial_id)
    except Exception:
        with _LOCK:
            _ACTIVE.discard((str(Path(root)), trial_id))
            _CANCEL.pop((str(Path(root)), trial_id), None)
            _READINESS.pop((str(Path(root)), trial_id), None)
        record.update(status='interrupted', error='Worker could not start. Review and approve resume.')
        write(root, record)
        raise
    return record
