from app.db import session_scope
from app.models.user import User
from app.models.project import Project, ProjectStatus
from app.models.source_video import SourceVideo, SourceVideoStatus
from app.models.segment import Segment, SegmentStatus
from app.models.speaker import Speaker

def seed():
    with session_scope() as db:
        # Check or create dev@sur.ai
        user = db.query(User).filter(User.email == "dev@sur.ai").first()
        if not user:
            user = User(email="dev@sur.ai")
            db.add(user)
            db.flush()

        # Check if project already exists
        existing = db.query(Project).filter(Project.user_id == user.id).first()
        if existing:
            print("Project already seeded for dev@sur.ai:", existing.id)
            return

        project = Project(
            user_id=user.id,
            title="Kalki 2898 AD Teaser Breakdown",
            target_languages=["te", "ta"],
            status=ProjectStatus.processing,
            current_stage="synthesize",
            preserve_emotion=True,
            clone_voice=True,
            lip_sync_aware=True,
            tts_model="cosyvoice2",
        )
        db.add(project)
        db.flush()

        video = SourceVideo(
            project_id=project.id,
            original_filename="kalki_teaser_source.mp4",
            content_type="video/mp4",
            storage_key=f"projects/{project.id}/videos/kalki_teaser_source.mp4",
            status=SourceVideoStatus.uploaded,
            duration_ms=194000,
        )
        db.add(video)
        db.flush()

        spk1 = Speaker(project_id=project.id, diarization_tag="SPEAKER_00", label="Narrator / Bhairava")
        spk2 = Speaker(project_id=project.id, diarization_tag="SPEAKER_01", label="Ashwatthama")
        db.add_all([spk1, spk2])
        db.flush()

        segments_data = [
            (0, spk1.id, 0, 3200, "Stand your ground! We do not surrender today.", "మీ స్థానంలో నిలబడండి! ఈరోజు మనం లొంగిపోము.", "anger", 0.94),
            (1, spk2.id, 3500, 7800, "I gave my word to the people, and I intend to keep it until my last breath.", "నేను ప్రజలకు మాట ఇచ్చాను, నా చివరి శ్వాస వరకు దాన్ని నిలబెట్టుకుంటాను.", "happiness", 0.88),
            (2, spk1.id, 8200, 12400, "Then let the fire burn through every obstacle before us.", "అయితే మన ముందున్న ప్రతి అడ్డంకిని అగ్ని దహించివేయనివ్వండి.", "anger", 0.96),
            (3, spk2.id, 13000, 16800, "The prophecy speaks of one who will shatter the darkness of Kasi.", "కాశీలోని చీకటిని చీల్చివేసే వ్యక్తి గురించి పురాణం చెబుతోంది.", "sadness", 0.72),
            (4, spk1.id, 17500, 21900, "No darkness withstands our courage when we unite as one.", "మనం ఒక్కటిగా కలిసినప్పుడు ఏ చీకటి కూడా మన ధైర్యాన్ని తట్టుకోలేదు.", "happiness", 0.91),
        ]

        for idx, spk, s_ms, e_ms, src, trn, emo, score in segments_data:
            seg = Segment(
                project_id=project.id,
                source_video_id=video.id,
                index=idx,
                speaker_id=spk,
                start_ms=s_ms,
                end_ms=e_ms,
                source_text=src,
                translated_text=trn,
                emotion_label=emo,
                emotion_score=score,
                emotion_overridden=False,
                tts_duration_ms=int((e_ms - s_ms) * 0.98),
                sync_offset_pct=-2.0,
                status=SegmentStatus.synthesized,
            )
            db.add(seg)

        print(f"Seeded project {project.id} with {len(segments_data)} segments!")

if __name__ == "__main__":
    seed()
