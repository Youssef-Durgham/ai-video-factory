# YouTube Content Policies Reference
## For AI Video Factory — Phase 4 Compliance Checkers

> **Last Updated:** March 2026
> This document summarizes YouTube's policies relevant to AI-generated Arabic documentary content.
> Used by `src/phase4_compliance/` to validate scripts before production.

---

## 1. Monetization Requirements (YPP)

### Eligibility
- 1,000+ subscribers
- 4,000+ public watch hours (last 12 months) OR 10M+ Shorts views (last 90 days)
- AdSense account linked
- No active community guideline strikes
- Two-step verification enabled

### Content That Cannot Be Monetized
- Reused content without significant commentary/education
- AI-generated content that is "low effort" or "mass produced"
- Content with no clear educational, documentary, or entertainment value
- Videos shorter than 8 minutes cannot have mid-roll ads
- Content made "primarily for kids" (limited ad formats)

### Ad-Friendly Content Guidelines
- **Avoid:** Excessive profanity, violence, drug use, sexual content, controversial/sensitive topics without educational context
- **Safe:** Educational documentaries, historical analysis, science explainers, cultural content

---

## 2. Community Guidelines

### Violence & Graphic Content
- ❌ Gratuitous violence, gore, graphic injuries
- ❌ Glorification of violence or dangerous acts
- ✅ Educational/documentary context with appropriate framing
- ✅ Historical footage with content warning
- ⚠️ War/conflict documentaries: must provide educational context, not glorify

### Sexual Content
- ❌ Any sexually explicit or suggestive content
- ❌ Nudity (even artistic/educational has restrictions)
- ✅ Educational health/anatomy content with clinical framing
- ⚠️ AI-generated images: extra scrutiny for inadvertent NSFW elements

### Misinformation
- ❌ Medical misinformation (vaccines, treatments, COVID)
- ❌ Election/civic misinformation
- ❌ Dangerous conspiracy theories presented as fact
- ✅ Presenting conspiracy theories as theories with debunking/context
- ✅ Historical analysis of propaganda (clearly labeled)
- ⚠️ Fact-check all statistical claims (minimum 2 independent sources)

### Copyrighted Material
- ❌ Copyrighted music (even short clips can trigger Content ID)
- ❌ Reused footage without license
- ✅ AI-generated music (original, no training on copyrighted works)
- ✅ Royalty-free SFX and ambient sounds
- ⚠️ Content ID system is automated — false positives possible
- ⚠️ ACE-Step 1.5 generated music: run through Content ID pre-check

### Hate Speech
- ❌ Content promoting hatred against protected groups
- ❌ Dehumanizing language
- ✅ Educational discussion of historical discrimination/persecution
- ⚠️ Arabic content: be careful with sectarian language

### Harassment & Cyberbullying
- ❌ Targeting individuals with malicious intent
- ✅ Public figure criticism with factual basis
- ⚠️ Documentary coverage of living people: balanced, sourced

---

## 3. AI Content Disclosure Rules (2026)

### YouTube's AI Disclosure Requirements
- **Mandatory disclosure** when AI is used to generate realistic-looking content
- Must use YouTube's "Altered or Synthetic Content" label
- Applies to: AI-generated images, video, voice
- **Documentary context:** Still requires disclosure even if educational
- **Penalty for non-disclosure:** Content removal, channel strike

### How to Comply
1. Add "Altered or Synthetic Content" label during upload
2. Include disclosure in video description:
   ```
   هذا الفيديو يستخدم محتوى مُنشأ بالذكاء الاصطناعي لأغراض توضيحية وتعليمية.
   This video uses AI-generated content for illustrative and educational purposes.
   ```
3. If depicting real events: clearly state that visuals are AI-generated representations
4. If depicting real people: explicit AI disclosure overlay in video

### AI-Specific Content Policies (2026)
- AI-generated content must provide "significant value" (education, entertainment, creativity)
- "Low-effort" AI content (slideshow + TTS) faces reduced reach
- AI voices: must not impersonate real people without consent
- AI deepfakes of real people: prohibited unless clearly labeled satire/parody

---

## 4. Arabic Content Specific Guidelines

### Language Standards
- Modern Standard Arabic (MSA/فصحى) preferred for broad reach
- Dialectal Arabic acceptable for targeted audiences
- Avoid mixing Arabic and English unnecessarily
- Proper diacritics (تشكيل) for Quranic/classical quotes

### Cultural Sensitivity
- **Religious content:** Respectful treatment required; no mockery
- **Political content:** Present multiple perspectives; avoid propaganda
- **Sectarian issues:** Extremely sensitive; avoid taking sides
- **Israel-Palestine:** Follow YouTube's specific policies on conflict content
- **Historical events:** Frame as educational; cite academic sources

### Regional Considerations
- Content accessible in Saudi Arabia, UAE, Egypt, Iraq, etc.
- Some topics are locally sensitive (e.g., local politics, royal families)
- Avoid content that could be considered "insulting to religion" (broad interpretation in MENA)

### Monetization for Arabic Content
- Arabic content RPM generally lower than English ($1-5 vs $5-15)
- Higher RPM topics: technology, finance, education, health
- Lower RPM topics: entertainment, music, vlogs
- Gulf audience (KSA, UAE) has higher RPM than North Africa

---

## 5. Compliance Checker Implementation Notes

### Pre-Production Checks (Phase 4)
```
For each script, verify:
1. No direct quotes of copyrighted material
2. All factual claims have 2+ sources
3. No hate speech or discriminatory language
4. Sensitive topics have educational framing
5. No medical/election misinformation
6. AI disclosure text included in metadata template
7. No real person depicted without factual basis
8. Religious references are respectful and accurate
```

### Post-Production Checks (Phase 7)
```
For each video, verify:
1. AI-generated music passes Content ID pre-check
2. No NSFW elements in AI-generated images
3. Text overlays don't contain copyrighted text
4. AI disclosure label ready for upload
5. Description includes AI disclosure statement
```

### Auto-Block Triggers
These findings should BLOCK the job and alert human:
- NSFW content detected in any image
- Copyright match in audio fingerprint
- Medical misinformation keywords without educational context
- Real person depicted (face detection + name in script)
- Sectarian language detected
- Active conflict region depicted without balanced framing

---

## 6. References

- [YouTube Community Guidelines](https://www.youtube.com/howyoutubeworks/policies/community-guidelines/)
- [YouTube Advertiser-Friendly Guidelines](https://support.google.com/youtube/answer/6162278)
- [YouTube AI Content Policy 2026](https://support.google.com/youtube/answer/13084870)
- [YouTube Partner Program Policies](https://support.google.com/youtube/answer/72851)
