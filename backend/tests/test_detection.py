import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.intent_router import analyze_intent

TEST_CASES = [
    # SHOULD BE NORMAL
    ("Normal greeting",           "Hello how are you",                                          None,     False),
    ("Okay check in",             "I'm feeling okay today",                                     None,     False),
    ("Study frustration",         "ayoko na mag aral",                                          None,     False),
    ("General tiredness",         "pagod na ako",                                               None,     False),
    ("Breakup alone",             "I broke up with my partner",                                 None,     False),
    ("Mild sad",                  "I feel a bit sad today",                                     None,     False),
    ("Tired of studying",         "I'm tired of studying",                                      None,     False),
    ("Bored",                     "wala lang bored lang ako",                                   None,     False),
    ("Just kidding",              "just kidding",                                               None,     False),
    ("Good morning",              "good morning",                                               None,     False),
    ("Okay na",                   "okay na ako",                                                None,     False),
    ("Dying of laughter",         "im dying of laughter",                                      None,     False),
    ("Friend stressed",           "my friend is stressed",                                      None,     False),

    # SHOULD BE LOW
    ("Exam stress",               "I've been stressed about my exams lately I can't focus",    "low",    False),
    ("General worry",             "I keep worrying about small things",                         "low",    False),
    ("Mild anxiety",              "I feel nervous about tomorrow",                              "low",    False),
    ("Mild lonely",               "I feel lonely today",                                        "low",    False),

    # SHOULD BE MODERATE
    ("Persistent stress",         "I can't sleep I can't focus everything is piling up",       "moderate", False),
    ("Hopelessness mild",         "I feel hopeless about my future",                           "moderate", False),
    ("Burnout",                   "I feel burned out I have no energy left",                   "moderate", False),

    # SHOULD BE HIGH — alert fires
    ("Physical symptoms",         "I can't stop shaking my chest is tight I can't breathe",   "high",   True),
    ("Panic attack",              "I'm having a panic attack right now",                       "high",   True),
    ("Strong hopeless",           "I feel completely worthless and broken I don't know why I keep trying", "high", True),

    # SHOULD BE CRISIS — alert fires
    ("Direct suicidal EN",        "I want to kill myself",                                     "crisis", True),
    ("Direct suicidal EN slang",  "i gonna kill myself",                                     "crisis", True),
    ("STT-spaced kill myself",    "im gonna kill my self",                                    "crisis", True),
    ("KMS slang short",           "kms",                                                      "crisis", True),
    ("KMS slang sentence",        "i will kms",                                               "crisis", True),
    ("Off myself",                "i will off myself",                                        "crisis", True),
    ("Let me just die",           "let me just die",                                          "crisis", True),
    ("Maybe I should just die",   "maybe i should just die",                                  "crisis", True),
    ("Hurt myself",               "i want to hurt myself",                                    "crisis", True),
    ("End my life tonight",       "i want to end my life tonight",                            "crisis", True),
    ("Filipino mawala",           "gusto ko nang mawala",                                     "crisis", True),
    ("Third-person disclosure",   "my friend said she wants to kill herself",                 "high",  True),
    ("Fiction kills herself",     "the character kills herself in that movie",                None,    False),
    ("Idiom class kills me",      "this class is killing me",                                 None,    False),
    ("Direct suicidal PH",        "gusto ko na mamatay",                                       "crisis", True),
    ("Direct suicidal PH 2",      "magpapakamatay na ako",                                     "crisis", True),
    ("Indirect end it all",       "I feel I should end it all",                                "crisis", True),
    ("Indirect point of living",  "I don't know if there's a point of living anymore",         "crisis", True),
    ("Indirect no reason",        "what's the point of living anymore",                        "crisis", True),
    ("Indirect Filipino",         "wala na akong dahilan para mabuhay",                        "crisis", True),
    ("Indirect Filipino 2",       "para saan pa mabuhay",                                      "crisis", True),
    ("Indirect done with life",   "I'm done with life",                                        "crisis", True),
    ("Indirect want it to stop",  "I just want it all to stop permanently",                    "crisis", True),
    ("Breakup suicidal",          "she broke up with me I don't know if there's a point of living anymore", "crisis", True),
    ("No point anymore",          "there's no point anymore",                                  "crisis", True),
    ("Di ko na kaya buhay",       "di ko na kaya ang buhay",                                   "crisis", True),
]


def run_tests():
    passed = 0
    failed = 0
    errors = []

    print("\n" + "═" * 65)
    print("  GAIDA DETECTION TEST SUITE")
    print("═" * 65)

    for description, message, expected_level, should_alert in TEST_CASES:
        try:
            result = analyze_intent(user_message=message, session_id=None)

            actual_level = result.get("anxiety_level")
            actual_alert = result.get("anxiety_level") in ("high", "crisis")

            level_pass = actual_level == expected_level
            alert_pass = actual_alert == should_alert

            if level_pass and alert_pass:
                print(f"  ✅ PASS  {description}")
                print(f"          level={actual_level}\n")
                passed += 1
            else:
                print(f"  ❌ FAIL  {description}")
                print(f"          '{message[:60]}{'...' if len(message) > 60 else ''}'")
                if not level_pass:
                    print(f"          level:  expected={expected_level}  got={actual_level}")
                if not alert_pass:
                    print(f"          alert:  expected={should_alert}  got={actual_alert}")
                print()
                failed += 1
                errors.append({
                    "description": description,
                    "message": message,
                    "expected_level": expected_level,
                    "actual_level": actual_level,
                    "expected_alert": should_alert,
                    "actual_alert": actual_alert,
                })

        except Exception as e:
            print(f"  💥 ERROR {description}: {e}\n")
            failed += 1

    print("═" * 65)
    print(f"  RESULTS: {passed} passed, {failed} failed out of {len(TEST_CASES)} tests")
    print("═" * 65)

    if errors:
        print("\n  FAILED CASES:")
        for e in errors:
            print(f"  • {e['description']}")
            print(f"    expected={e['expected_level']} got={e['actual_level']} | alert expected={e['expected_alert']} got={e['actual_alert']}")
    print()

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)