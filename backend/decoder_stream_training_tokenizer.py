"""Tokenizer contract for a separately approved manual twenty-step streamed trial."""
import math
import re
if __package__:
    from .decoder_stream_model_tokenizer import StreamModelTokenizer
    from .run_manifest import digest
else:
    from decoder_stream_model_tokenizer import StreamModelTokenizer
    from run_manifest import digest

FORMAT='almg-approved-stream-training-tokenizer-v1'
SETTINGS={'total_steps':20,'chunk_steps':5,'batch_windows':4,'learning_rate':.05,'seed':7,'context_length':16,'width':8,'quality_target':.8}


class StreamTrainingTokenizer(StreamModelTokenizer):
    def artifact(self):
        value=super().artifact();value.update(format=FORMAT,scope='separately_approved_manual_stream_sgd20_trial',training_approved=True)
        return value

    @classmethod
    def restore(cls,artifact):
        if (not isinstance(artifact,dict) or set(artifact)!={'format','schema_version','codec','selection','scope','input_policy','generated_decode_policy','training_approved','release_approved'}
                or artifact.get('format')!=FORMAT or type(artifact.get('schema_version')) is not int):raise ValueError('Unsupported approved stream training tokenizer artifact.')
        result=cls(artifact['codec'],artifact['selection'])
        if digest(artifact)!=digest(result.artifact()):raise ValueError('Approved stream training tokenizer policy changed.')
        return result

    def validate_training_record(self,record):
        fields={'kind','schema_version','approval','approval_sha256','completed_steps','train_cursor','training_targets','training_loss_sum',
                'source_batch_chain_sha256','previous_checkpoint_sha256','evaluation_sha256','pretrained_weights_loaded','model_training_approved','release_approved'}
        if (not isinstance(record,dict) or set(record)!=fields or record.get('kind')!='stream_optimizer_checkpoint'
                or type(record.get('schema_version')) is not int or record['schema_version']!=1
                or type(record.get('completed_steps')) is not int or not 0<=record['completed_steps']<=20 or record['completed_steps']%5
                or type(record.get('training_targets')) is not int or record['training_targets']<0
                or type(record.get('training_loss_sum')) not in (int,float) or not math.isfinite(record['training_loss_sum']) or record['training_loss_sum']<0
                or record.get('model_training_approved') is not True or record.get('pretrained_weights_loaded') is not False or record.get('release_approved') is not False):
            raise ValueError('Approved stream checkpoint settings or scope are invalid.')
        approval=record['approval']
        cursor=record['train_cursor']
        if cursor is not None and (not isinstance(cursor,dict) or set(cursor)!={'revision','after_group','after_offset','split'}
                or cursor.get('revision')!=self.selection['windows_revision'] or cursor.get('split')!='train'
                or not isinstance(cursor.get('after_group'),str) or not re.fullmatch('[a-f0-9]{64}',cursor['after_group'])
                or type(cursor.get('after_offset')) is not int or cursor['after_offset']<0):raise ValueError('Checkpoint training cursor changed.')
        if (not isinstance(approval,dict) or set(approval)!={'version','scope','windows_id','windows_revision','tokenizer_sha256','settings','implementation_sha256'}
                or type(approval.get('version')) is not int or approval['version']!=1
                or approval.get('scope')!='manual_stream_sgd20_trial' or digest(approval.get('settings'))!=digest(SETTINGS)
                or not isinstance(approval.get('implementation_sha256'),str) or not re.fullmatch('[a-f0-9]{64}',approval['implementation_sha256'])
                or any(approval.get(key)!=self.selection[key] for key in ('windows_id','windows_revision','tokenizer_sha256'))
                or record['approval_sha256']!=digest(approval) or record['approval_sha256']!=self.selection['approval_sha256']):
            raise ValueError('Stream training approval binding changed.')
        if (record['completed_steps']==0 and (record['training_targets']!=0 or record['training_loss_sum']!=0 or cursor is not None or record['previous_checkpoint_sha256'] is not None)
                or record['completed_steps']>0 and (record['training_targets']<=0 or record['previous_checkpoint_sha256'] is None)):
            raise ValueError('Checkpoint progress and lineage disagree.')
        for key in ('source_batch_chain_sha256','evaluation_sha256'):
            if not isinstance(record[key],str) or not re.fullmatch('[a-f0-9]{64}',record[key]):raise ValueError('Checkpoint lineage hash changed.')
        if record['previous_checkpoint_sha256'] is not None and (not isinstance(record['previous_checkpoint_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',record['previous_checkpoint_sha256'])):
            raise ValueError('Previous checkpoint hash changed.')
