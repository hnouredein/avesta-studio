#!/usr/bin/env python3
"""Rebuild rafah_woman timeline captions from the verified medium-q5 transcript.
text = Arabic (primary, karaoke), en_text = English verbatim (subtitle pill).
words left empty so karaoke timing distributes evenly across the chunk.
"""
import json
import os

JOB = os.path.expanduser("~/avesta/Avesta-Studio/videos/rafah_woman")
TL = os.path.join(JOB, "work", "timeline_data.json")
WORDS_JSON = "/tmp/wtest/rafah_words.json"

# (first_word_idx, last_word_idx_inclusive, english, arabic)
CHUNKS = [
    (0, 11, "I wanted to share this video of what this young Egyptian woman said", "أردت مشاركة هذا الفيديو لما قالته هذه الشابة المصرية"),
    (12, 17, "to CNN's Clarissa Ward,", "لمراسلة CNN كلاريسا وارد"),
    (19, 28, "she is on the Egyptian side of the border,", "وهي على الجانب المصري من الحدود"),
    (29, 32, "take a listen.", "استمعوا"),
    (33, 41, "Excuse me, where is your condemnation?", "عذراً، أين إدانتكم؟"),
    (42, 48, "Where is your channel covering this?", "أين تغطية قناتكم لهذا؟"),
    (49, 51, "Cover this!", "غطّوا هذا!"),
    (52, 55, "Say the truth,", "قولوا الحقيقة"),
    (56, 62, "we understand you're an employee,", "نحن نفهم أنكِ موظفة"),
    (63, 68, "you're just a puppet,", "لكنكِ مجرد دمية"),
    (69, 74, "you're just a mouthpiece.", "أنتِ مجرد بوق."),
    (75, 83, "Come talk to me like a human being.", "تعالي وتحدثي معي كإنسانة"),
    (84, 92, "Come talk to me like a human being.", "تعالي وتحدثي معي كإنسانة"),
    (93, 95, "Thank you.", "شكراً."),
    (96, 103, "I understand you have your foreign policy.", "أتفهم أن لديكم سياستكم الخارجية."),
    (104, 110, "No, I've heard you.", "لا، لقد سمعتُكِ."),
    (111, 115, "I've heard you.", "لقد سمعتُكِ."),
    (116, 119, "You hear me.", "اسمعيني."),
    (120, 127, "I understand you have your foreign policy.", "أتفهم أن لديكم سياستكم الخارجية."),
    (128, 135, "I understand you speak for your government.", "أتفهم أنكِ تتحدثين باسم حكومتكِ."),
    (136, 142, "I understand you represent your government.", "أتفهم أنكِ تمثلين حكومتكِ."),
    (143, 147, "With that being said,", "ومع ذلك،"),
    (148, 156, "you're a country that claims free speech.", "أنتم دولة تدّعي حرية التعبير."),
    (157, 167, "Your customized democracy is actually what led to Hamas.", "ديمقراطيتكم المفصّلة هي التي أدت إلى حماس."),
    (168, 175, "And now, we are watching an occupation", "والآن، نشاهد احتلالاً"),
    (176, 184, "and we are watching the result of your silence,", "ونشاهد نتيجة صمتكم،"),
    (186, 194, "of your misrepresentation of Arabs.", "وتشويهكم لصورة العرب."),
    (195, 201, "And we stand with the Palestinians,", "ونحن نقف مع الفلسطينيين،"),
    (202, 207, "and we stand with Arabs,", "ونقف مع العرب،"),
    (208, 215, "and they try and change the narrative", "ويحاولون تغيير الرواية"),
    (216, 222, "because you own the narrative, see?", "لأنكم تملكون الرواية، أترون؟"),
    (223, 227, "This is our problem.", "هذه هي مشكلتنا."),
    (228, 232, "You own the narrative,", "أنتم تملكون الرواية،"),
    (233, 238, "you own the United Nations,", "وتملكون الأمم المتحدة،"),
    (239, 242, "you own Hollywood,", "وتملكون هوليوود،"),
    (243, 249, "you own all these mouthpieces.", "وتملكون كل هذه الأبواق."),
    (250, 254, "Where are our voices?", "أين أصواتنا؟"),
    (255, 263, "Our voices need to be heard as well.", "يجب أن تُسمع أصواتنا أيضاً."),
    (264, 270, "We've been watching your channel,", "لقد كنا نشاهد قناتكم،"),
    (271, 277, "and instead of mourning our dead,", "وبدلاً من الحداد على موتانا،"),
    (278, 284, "instead of mourning these Palestinian children,", "وبدلاً من الحداد على هؤلاء الأطفال الفلسطينيين،"),
    (285, 298, "we've been having to deal with more dehumanization of Arabs.", "كان علينا التعامل مع مزيد من نزع الإنسانية عن العرب."),
]

def main():
    d = json.load(open(WORDS_JSON, encoding="utf-8-sig"))
    words = []
    for seg in d["transcription"]:
        t = seg["text"].strip()
        if t:
            words.append((seg["offsets"]["from"] / 1000, seg["offsets"]["to"] / 1000, t))
    assert len(words) >= 299, f"expected ~299 words, got {len(words)}"

    tl = json.load(open(TL, encoding="utf-8-sig"))
    dur = float(tl.get("duration") or 78.0)

    caps = []
    for cid, (a, b, en, ar) in enumerate(CHUNKS):
        start = round(words[a][0], 3)
        end = round(min(words[b][1] + 0.12, dur - 0.05), 3)
        caps.append({
            "id": cid,
            "start": start,
            "end": end,
            "text": ar,
            "en_text": en,
            "highlight": "",
            "broll": "",
            "zoom": False,
            "words": [],
        })

    tl["captions"] = caps
    tl["teaser_duration"] = 0.0
    tl["teaser_source_start"] = 0.0
    json.dump(tl, open(TL, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"wrote {len(caps)} captions, duration {dur}")

if __name__ == "__main__":
    main()
