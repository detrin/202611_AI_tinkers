# Hackathon Idea: Personal Wardrobe Agent
**Working Name: Good Enough**

### 1. Problem

Choosing what to wear is a small but repetitive, time-consuming task that happens every morning.

Even people who aren't particularly interested in fashion still want to look appropriate, feel comfortable, and maintain their personal style.

Every morning, people need to consider:

- **Weather:** What's the temperature? Will it rain?
- **Schedule & Occasion:** What am I doing today? How formal should I dress?
- **Personal Preference:** What kind of look or mood do I want?
- **Existing Wardrobe:** What do I actually own, and what goes well together?

Individually, these decisions seem trivial. But combining all these factors every morning requires time and mental effort.

**Our insight:** People don't necessarily want to become better at fashion. They want to spend less time thinking about what to wear, without looking out of place.

**Our goal:** Build an AI agent that handles these decisions and recommends outfits using clothes the user already owns.

### 2. Core Features (MVP)

**1. Build a Digital Wardrobe — Two Input Methods**

Users can register clothes they actually own through two methods:

**A. Photo Upload**
- Take or upload a photo of an existing clothing item.
- Optionally add a short description.
- AI identifies its attributes and adds it to the wardrobe.

**B. Product URL — Powered by Apify**
- Paste a shopping link for an item the user owns.
- Apify extracts product images, descriptions, and available metadata.
- AI analyzes and categorizes the clothing item.
- The user confirms the correct product variant when necessary.

Both methods save items in the **same structured wardrobe database**.

**2. Structured Clothing Data**

Each registered item should have a standardized set of attributes:

| Attribute | Example |
|---|---|
| Category | Shirt, Pants, Jacket, Shoes |
| Color | Navy, Beige, Black |
| Pattern | Solid, Striped, Checked |
| Season / Warmth | Summer, Winter, Lightweight |
| Formality | Casual, Smart Casual, Formal |
| Style / Fit | Minimal, Relaxed, Slim |
| Availability | Available, Laundry |
| Image / Source | Uploaded Photo, Product URL |

AI automatically extracts these attributes when possible. Users can review or correct them, and uncertain attributes can remain unspecified.

These structured attributes will help the recommendation agent consistently evaluate clothing combinations.

**3. Calendar + Weather-Based Outfit Recommendations**

- Integrate Google Calendar API to understand the user's schedule and occasions.
- Integrate a Weather API for temperature, precipitation, and other conditions.
- Consider personal style preferences and clothing attributes.
- **Only recommend clothing items registered in the user's wardrobe.**

**4. Dynamic Replanning Based on User Feedback**

- Example: "Those pants are in the laundry."
- The agent updates the item's availability in the database.
- It generates a new outfit using other available items.

**5. Personal Style / Mood Preferences**

- Users provide reference images representing their preferred aesthetic.
- AI identifies style preferences such as colors, fit, and overall mood.
- The recommendation agent incorporates these preferences.
- If time permits, Apify can collect publicly available inspiration images from platforms such as Pinterest.

### 3. Core User Flow

1. **Register clothes:** Upload photos or paste product URLs.
2. **Categorize:** AI extracts standardized clothing attributes and builds the digital wardrobe.
3. **Set preferences:** Select or upload reference images for a preferred style.
4. **Understand context:** The agent checks calendar events and weather conditions.
5. **Recommend:** Select an appropriate outfit from the user's existing wardrobe and explain why.
6. **Replan:** Update clothing availability and recommend alternatives based on user feedback.

### 4. Six-Hour Hackathon Scope

**Must Have**
- Clothing registration via photo upload or Apify product extraction.
- Standardized clothing attributes stored in a digital wardrobe.
- Outfit recommendations using registered items only.
- Weather, occasion, and basic personal style considered in recommendations.
- Clothing availability updates and dynamic replanning.

**Simplifications**
- Support 1–2 tested e-commerce websites initially.
- Use a small predefined set of clothing categories and attributes.
- Allow direct image uploads for mood references.
- Use manual event input if Google Calendar OAuth becomes a blocker.
- Focus on one complete, reliable user journey.

**Out of Scope**
- Virtual try-on
- Shopping and advertising integrations
- Support for every e-commerce website
- Advanced personalization and long-term learning

### 5. Judging Criteria & Demo Goal

**Key judging criteria:** Creativity, solving a real problem based on a real insight, accurate live demonstration, and meaningful use of Apify.

**Our differentiation:** Rather than helping fashion enthusiasts discover more clothes, we reduce everyday decision-making effort for people who don't want to spend much time thinking about fashion.

**Live Demo Flow:**

Photo / Product URL → Apify extraction or AI image analysis → Structured digital wardrobe → Calendar + Weather + Style Preferences → Outfit recommendation from owned clothes → User feedback → Updated recommendation.

The goal is to demonstrate one complete, working agent workflow rather than many disconnected features.

### 6. Future Opportunities (Post-Hackathon)

- Learn preferences from outfit choices and feedback.
- Track outfit history and wardrobe usage.
- Identify gaps in the user's wardrobe.
- Recommend useful purchases that complement existing clothes.
- Explore brand partnerships and commerce integrations.

**Core principle:** Help people make better use of what they already own before encouraging them to buy more.

---

**One-line Pitch**

*An AI wardrobe agent that checks your weather, calendar, personal style, and existing clothes — so you don't have to figure out what to wear every morning.*
