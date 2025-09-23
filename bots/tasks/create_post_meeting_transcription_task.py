import logging

from celery import shared_task
from django.utils import timezone

from bots.models import RecordingArtifact, RecordingArtifactManager, RecordingArtifactStates, RecordingArtifactTypes, TranscriptionFailureReasons, Utterance
from bots.tasks.process_utterance_task import process_utterance

logger = logging.getLogger(__name__)


def create_utterances_for_transcription(recording_artifact):
    recording = recording_artifact.recording

    # Get all the audio chunks for the recording
    # then create utterances for each audio chunk
    for audio_chunk in recording.audio_chunks.all():
        utterance = Utterance.objects.create(
            source=Utterance.Sources.PER_PARTICIPANT_AUDIO,
            recording=recording,
            recording_artifact=recording_artifact,
            participant=audio_chunk.participant,
            audio_chunk=audio_chunk,
            timestamp_ms=audio_chunk.timestamp_ms,
            duration_ms=audio_chunk.duration_ms,
        )

        process_utterance.delay(utterance.id)

    # After the utterances have been created and queued for transcription, set the recording artifact to in progress
    RecordingArtifactManager.set_recording_artifact_in_progress(recording_artifact)


def terminate_transcription(recording_artifact):
    # We'll mark it as failed if there are any failed utterances or any in progress utterances
    any_in_progress_utterances = recording_artifact.utterances.filter(transcription__isnull=True, failure_data__isnull=True).exists()
    any_failed_utterances = recording_artifact.utterances.filter(failure_data__isnull=False).exists()
    if any_failed_utterances or any_in_progress_utterances:
        failure_reasons = list(recording_artifact.utterances.filter(failure_data__has_key="reason").values_list("failure_data__reason", flat=True).distinct())
        if any_in_progress_utterances:
            failure_reasons.append(TranscriptionFailureReasons.UTTERANCES_STILL_IN_PROGRESS_WHEN_TRANSCRIPTION_TERMINATED)
        RecordingArtifactManager.set_recording_artifact_failed(recording_artifact, failure_data={"failure_reasons": failure_reasons})
    else:
        RecordingArtifactManager.set_recording_artifact_complete(recording_artifact)


def check_for_transcription_completion(recording_artifact):
    in_progress_utterances = recording_artifact.utterances.filter(transcription__isnull=True, failure_data__isnull=True)

    # If no in progress utterances exist or it's been more than 30 minutes, then we need to terminate the transcription
    if not in_progress_utterances.exists() or timezone.now() - recording_artifact.started_at > timezone.timedelta(minutes=30):
        logger.info(f"Terminating transcription for recording artifact {recording_artifact.id} because no in progress utterances exist or it's been more than 30 minutes")
        terminate_transcription(recording_artifact)
        return

    # An in progress utterance exists and we haven't timed out, so we need to check again in 2 minutes
    logger.info(f"Checking for transcription completion for recording artifact {recording_artifact.id} again in 2 minutes")
    create_post_meeting_transcription.apply_async(args=[recording_artifact.id], countdown=120)


@shared_task(
    bind=True,
    soft_time_limit=3600,
)
def create_post_meeting_transcription(self, post_meeting_transcription_recording_artifact_id):
    recording_artifact = RecordingArtifact.objects.filter(artifact_type=RecordingArtifactTypes.POST_MEETING_TRANSCRIPTION).get(id=post_meeting_transcription_recording_artifact_id)

    try:
        if recording_artifact.state == RecordingArtifactStates.COMPLETE or recording_artifact.state == RecordingArtifactStates.FAILED:
            return

        if recording_artifact.state == RecordingArtifactStates.NOT_STARTED:
            create_utterances_for_transcription(recording_artifact)

        check_for_transcription_completion(recording_artifact)

    except Exception as e:
        logger.exception(f"Unexpected exception in create_post_meeting_transcription: {str(e)}")
        RecordingArtifactManager.set_recording_artifact_failed(recording_artifact, failure_data={})
