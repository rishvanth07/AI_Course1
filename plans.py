"""Lesson plans drafted from a course name and focus."""

import random
import secrets


TOPICS = (
    ("python", "code", "coding", "programming", "loop", "function"),
    ("calculus", "derivative", "integral", "math", "algebra"),
    ("write", "writing", "essay", "sentence", "grammar"),
    ("data", "chart", "statistics", "stats", "graph"),
    ("machine", "ml", "model", "ai", "neural"),
    ("system", "systems", "design", "debug", "bug"),
)


def _plain(value: str) -> str:
    return value.replace("{", "").replace("}", "").strip()


def plan_overview(title: str, goal: str) -> str:
    title = _plain(title) or "this course"
    goal = _plain(goal)
    if goal:
        return f"Four lessons on {title}, aimed at {goal}. Study a lesson, then take its quiz."
    return f"Four lessons on {title}. Study a lesson, then take its quiz."


def draft_plan(title: str, goal: str) -> list[dict]:
    title = _plain(title) or "this course"
    goal = _plain(goal)
    text = f"{title} {goal}".lower()
    rng = random.Random(f"{title}|{goal}")
    focus = goal.strip() or title.strip() or "the idea"
    for index, keys in enumerate(TOPICS):
        if any(key in text for key in keys):
            builders = (
                _python,
                _math,
                _writing,
                _data,
                _model,
                _systems,
            )
            return builders[index](title, focus, rng)
    return _general(title, focus, rng)


def _lesson(title: str, minutes: int, sections: list[tuple[str, str]], questions: list[dict]) -> dict:
    return {
        "id": secrets.token_hex(3),
        "title": title,
        "minutes": minutes,
        "sections": [{"label": label, "text": text} for label, text in sections],
        "quiz": questions,
        "studied": None,
        "attempts": [],
    }


def _ask(rng: random.Random, prompt: str, correct: str, wrongs: list[str]) -> dict:
    choices = [correct, *wrongs]
    rng.shuffle(choices)
    return {"prompt": prompt, "choices": choices, "answer": choices.index(correct)}


def _python(title: str, focus: str, rng: random.Random) -> list[dict]:
    return [
        _lesson(
            "A loop visits each item once",
            15,
            [
                ("Concept", "A loop walks a list from the first item to the last. The body runs once for each item, then stops."),
                ("Try", f"In {title}, write a loop that prints each word in a short list. Say out loud which word is next before it prints."),
                ("Check", "If the list has three words, the body runs three times. Count them."),
            ],
            [
                _ask(rng, "How many times does a loop body run?", "Once for each item in the list.", ["Once, no matter how long the list is.", "Forever, until you close the file."]),
                _ask(rng, "A list of three words means the body…", "Runs three times.", ["Runs once.", "Does not run, because words are text."]),
                _ask(rng, "The loop stops when…", "It has visited the last item.", ["The first item prints.", "You add a comment."]),
            ],
        ),
        _lesson(
            "The empty list",
            15,
            [
                ("Concept", f"An empty list has nothing to visit, so the body never runs. That is the useful part of “{focus}”: no items means no work inside the loop."),
                ("Try", "Run the same loop on []. Watch for a print. There should be none."),
                ("Check", "Say what you expected, then what happened. If they differ, the empty case is the lesson."),
            ],
            [
                _ask(rng, "What happens when a loop meets an empty list?", "The body never runs.", ["The body runs once with a blank item.", "Python fills the list for you."]),
                _ask(rng, "Why is the empty list worth testing?", "It shows the body is skipped when there is nothing to visit.", ["It makes the loop faster.", "It prints the word empty."]),
                _ask(rng, f"In this course, “{focus}” points at…", "What the loop does when there are no items.", ["How to sort a long list.", "How to install Python."]),
            ],
        ),
        _lesson(
            "The name after the loop",
            15,
            [
                ("Concept", "The loop variable keeps the last item it was given. If the body never ran, that name was never set by the loop."),
                ("Try", "After a loop over three words, print the loop variable. Then try the same after an empty list and notice the difference."),
                ("Check", "Guess the value first. Run it second. The guess is the point."),
            ],
            [
                _ask(rng, "After a loop over three words, the loop variable holds…", "The last word.", ["The first word.", "The number 3."]),
                _ask(rng, "If the body never ran, the loop variable…", "Was not set by the loop.", ["Becomes an empty string automatically.", "Holds every item at once."]),
                _ask(rng, "The useful order is…", "Guess, then run the code.", ["Run the code, then invent a reason.", "Skip the empty list."]),
            ],
        ),
        _lesson(
            "Hand the list to a function",
            20,
            [
                ("Concept", "A function can take the list as a parameter. The loop inside sees that list, not some other list with the same idea."),
                ("Try", "Write a function that prints each item. Call it once with words and once with an empty list."),
                ("Check", "Point at the parameter and say which list it is on each call."),
            ],
            [
                _ask(rng, "What does the loop inside the function walk?", "The list that was passed in.", ["Every list in the file.", "Only lists that are not empty."]),
                _ask(rng, "Two calls, one with words and one with [], should…", "Print the words, then print nothing.", ["Print the words twice.", "Refuse the empty list."]),
                _ask(rng, "You understand the function when you can…", "Say which list the parameter holds on each call.", ["Spell the function name.", "Add more arguments until it looks finished."]),
            ],
        ),
    ]


def _math(title: str, focus: str, rng: random.Random) -> list[dict]:
    return [
        _lesson(
            "Change at one moment",
            15,
            [
                ("Concept", f"In {title}, a derivative is how fast something is changing at one moment, not across a whole trip. Your focus is {focus}."),
                ("Try", "Pick a walk you know. Say whether you were speeding up, flat, or slowing down at one chosen moment."),
                ("Check", "If you described the whole walk, you have not picked a moment yet."),
            ],
            [
                _ask(rng, "A derivative describes…", "How fast a quantity is changing at one moment.", ["The total distance of a trip.", "The name of the curve."]),
                _ask(rng, "A description of the whole walk is…", "Too wide. Pick one moment.", ["Exactly a derivative.", "The slope at every point at once."]),
                _ask(rng, f"This course is aimed at…", focus, ["Memorizing a formula you do not use.", "Drawing a perfect circle."]),
            ],
        ),
        _lesson(
            "Slope on a hill",
            15,
            [
                ("Concept", "On a hill, slope is rise over a small step. A steep spot has a large slope. A flat spot has slope zero."),
                ("Try", "Sketch a hill. Mark one climbing spot, one flat spot, and one descending spot."),
                ("Check", "Point to the steepest mark and say the slope is largest there."),
            ],
            [
                _ask(rng, "A flat spot on the hill has slope…", "Zero.", ["The largest slope.", "A negative name, not a number."]),
                _ask(rng, "The steepest climbing spot has…", "The largest slope.", ["Slope zero.", "No slope, because it is steep."]),
                _ask(rng, "Slope compares…", "Rise over a small step.", ["The color of the hill.", "How long the walk took in total."]),
            ],
        ),
        _lesson(
            "Coming down",
            15,
            [
                ("Concept", "Coming down the hill, the quantity is decreasing, so the derivative is negative. Climbing is positive. Flat is zero."),
                ("Try", "Label your three marks +, 0, and −."),
                ("Check", "Read the labels back without looking at the sketch."),
            ],
            [
                _ask(rng, "A negative derivative means the quantity is…", "Decreasing.", ["Climbing.", "Unchanged."]),
                _ask(rng, "Climbing is marked…", "Positive.", ["Negative.", "Zero."]),
                _ask(rng, "Zero means…", "Flat at that moment.", ["The hill is finished.", "The derivative cannot be drawn."]),
            ],
        ),
        _lesson(
            "Say it without the sketch",
            15,
            [
                ("Concept", "You own the idea when you can say, for a new situation, whether the change is positive, zero, or negative."),
                ("Try", f"Take “{focus}” and name one moment that is climbing, one that is flat, and one that is coming down."),
                ("Check", "If you cannot name the flat moment, that is the next thing to find."),
            ],
            [
                _ask(rng, "You are ready to leave the sketch when you can…", "Call a new moment positive, zero, or negative.", ["Redraw the same hill from memory.", "Skip the flat spot."]),
                _ask(rng, "A moment you cannot label is…", "The next thing to study.", ["Proof that derivatives do not apply.", "Always the steepest spot."]),
                _ask(rng, "Positive, zero, and negative are…", "Climbing, flat, and coming down.", ["Three names for the same slope.", "Only used on the first hill."]),
            ],
        ),
    ]


def _writing(title: str, focus: str, rng: random.Random) -> list[dict]:
    return [
        _lesson(
            "One claim in a sentence",
            15,
            [
                ("Concept", f"A clear sentence in {title} makes one claim. Your focus is {focus}. The next sentence may add evidence, not a second claim."),
                ("Try", "Write one sentence that states only that focus. Stop when the claim is done."),
                ("Check", "If the sentence says “and” into a new idea, it still holds two claims."),
            ],
            [
                _ask(rng, "A clear sentence holds…", "One claim.", ["As many claims as the page allows.", "A claim and the evidence for a different claim."]),
                _ask(rng, "The next sentence should…", "Add evidence for that claim.", ["Start a second claim in the same breath.", "Repeat the first sentence."]),
                _ask(rng, "“And” that opens a new idea means…", "The sentence still holds two claims.", ["The sentence is finished.", "The claim is stronger."]),
            ],
        ),
        _lesson(
            "Split the muddy line",
            15,
            [
                ("Concept", "A muddy sentence is two ideas sharing a line. Split it until each piece says one thing."),
                ("Try", "Take a sentence you wrote and break it at every new claim."),
                ("Check", "Read each piece alone. It should still make sense."),
            ],
            [
                _ask(rng, "Splitting is done when…", "Each piece says one thing.", ["The paragraph is one long sentence.", "Every piece needs the others to mean anything."]),
                _ask(rng, "A muddy sentence usually…", "Holds two ideas.", ["Is too short to split.", "Has no claim."]),
                _ask(rng, "A piece that cannot stand alone…", "Still shares its idea with another piece.", ["Is the strongest sentence.", "Should be longer."]),
            ],
        ),
        _lesson(
            "Evidence in the next line",
            15,
            [
                ("Concept", "After the claim, one concrete detail is enough. A second claim disguised as a detail does not count."),
                ("Try", f"Under your sentence about {focus}, add one fact, example, or number."),
                ("Check", "Cover the claim and read the detail. It should support that claim, not replace it."),
            ],
            [
                _ask(rng, "The line after the claim should be…", "One concrete detail.", ["A new claim.", "A restatement with bigger words."]),
                _ask(rng, "A detail works when…", "It supports the claim you just made.", ["It introduces a second topic.", "It is longer than the claim."]),
                _ask(rng, "How much evidence belongs in the next line?", "One detail.", ["Every example you can remember.", "None. The claim is enough forever."]),
            ],
        ),
        _lesson(
            "Read it aloud",
            15,
            [
                ("Concept", "If you run out of breath, the line still holds two ideas. If you stumble on a word, you do not own it yet."),
                ("Try", "Read the claim and its one detail aloud, once."),
                ("Check", "Mark the word you could not say cleanly. That word is the next edit."),
            ],
            [
                _ask(rng, "Running out of breath means…", "The line still holds two ideas.", ["The claim is finally clear.", "You should read faster."]),
                _ask(rng, "A word you stumble on…", "Is the next edit.", ["Can stay, because you know what you meant.", "Should be replaced with a longer word."]),
                _ask(rng, "The aloud test uses…", "The claim and its one detail.", ["The whole essay.", "Only the title."]),
            ],
        ),
    ]


def _data(title: str, focus: str, rng: random.Random) -> list[dict]:
    return [
        _lesson(
            "The axis is part of the argument",
            15,
            [
                ("Concept", f"In {title}, the axis tells you what the marks mean. A cropped scale can make a small change look large. Your focus is {focus}."),
                ("Try", "Find one chart and write down what each axis measures."),
                ("Check", "If you cannot name both axes, you do not know the claim yet."),
            ],
            [
                _ask(rng, "Before you trust a chart, name…", "What each axis measures.", ["The colors first.", "Only the tallest bar."]),
                _ask(rng, "A cropped scale can…", "Make a small change look large.", ["Always show the true size.", "Remove the need for an axis."]),
                _ask(rng, "You do not know the claim yet when…", "You cannot name both axes.", ["The chart has a title.", "There are more than two bars."]),
            ],
        ),
        _lesson(
            "Where the scale starts",
            15,
            [
                ("Concept", "Ask where the vertical axis starts. Zero tells a different story from a start at 90."),
                ("Try", "On your chart, write the first labeled value on the vertical axis."),
                ("Check", "Say whether that value is zero."),
            ],
            [
                _ask(rng, "The first question about the vertical axis is…", "Where it starts.", ["Which bar is purple.", "How wide the chart is."]),
                _ask(rng, "Starting at 90 instead of 0 can…", "Exaggerate a small gap.", ["Make every comparison fair.", "Hide the bars."]),
                _ask(rng, "A scale that starts at zero…", "Shows the size against nothing.", ["Is always misleading.", "Cannot be drawn."]),
            ],
        ),
        _lesson(
            "Redraw from zero",
            15,
            [
                ("Concept", "Redraw the same points with a vertical axis that starts at zero. The story that survives is the one the data can support."),
                ("Try", "Sketch the bars again from zero, keeping their values."),
                ("Check", "Did the dramatic gap survive? If it shrank, the crop was doing the work."),
            ],
            [
                _ask(rng, "Redrawing from zero tests…", "Whether the story survives a fair scale.", ["Whether you can copy the title.", "Whether the bars should be horizontal."]),
                _ask(rng, "If the dramatic gap shrinks, then…", "The crop was doing the work.", ["The data got smaller.", "The chart was already fair."]),
                _ask(rng, "The story you keep is…", "The one that survives the redraw.", ["The one that looked largest at first.", "Any story the title suggests."]),
            ],
        ),
        _lesson(
            "Say what is still true",
            15,
            [
                ("Concept", "After the redraw, one sentence should say what is still true. That sentence is the chart’s claim."),
                ("Try", f"Write one sentence about {focus} that stays true when the axis starts at zero."),
                ("Check", "If the sentence needs the cropped axis, it is not the claim."),
            ],
            [
                _ask(rng, "The chart’s claim is…", "The sentence that stays true from zero.", ["The most alarming gap on the cropped axis.", "The title, whatever it says."]),
                _ask(rng, "A sentence that needs the cropped axis…", "Is not the claim.", ["Is the strongest finding.", "Should be the chart title."]),
                _ask(rng, "How many sentences should state the claim?", "One.", ["One per bar.", "None. Leave it visual."]),
            ],
        ),
    ]


def _model(title: str, focus: str, rng: random.Random) -> list[dict]:
    return [
        _lesson(
            "A model finds patterns in examples",
            15,
            [
                ("Concept", f"In {title}, a model finds patterns in the examples it was shown. It does not know the world those examples came from. Your focus is {focus}."),
                ("Try", "Name the task in one sentence, with no extra features."),
                ("Check", "If the sentence mentions the world outside the examples, you have skipped ahead."),
            ],
            [
                _ask(rng, "A model learns from…", "The examples it was shown.", ["The whole world, including what it never saw.", "The name of the task alone."]),
                _ask(rng, "What a model does not know is…", "The world those examples came from.", ["Any pattern in the examples.", "How to repeat a training example."]),
                _ask(rng, "The first sentence should name…", "The task, and nothing beyond it.", ["Every feature you might add later.", "The missing data."]),
            ],
        ),
        _lesson(
            "Three kinds of examples",
            15,
            [
                ("Concept", "A task needs more than one kind of example. Three kinds are enough to see what the model must be shown."),
                ("Try", f"For {focus}, list three kinds of examples a model would need."),
                ("Check", "Each kind should be different, not three copies of the same case."),
            ],
            [
                _ask(rng, "Why list three kinds?", "To see what the model must be shown.", ["Because three is always the size of the data.", "To avoid naming the task."]),
                _ask(rng, "Three copies of the same case…", "Do not count as three kinds.", ["Are a complete training set.", "Are better than different cases."]),
                _ask(rng, "The list belongs to…", "The task you named.", ["Any model, whatever it does.", "Only examples that are already correct."]),
            ],
        ),
        _lesson(
            "The situation you left out",
            15,
            [
                ("Concept", "The failure sits in a situation missing from the list. There the model can sound sure and be wrong."),
                ("Try", "Name one situation your three kinds do not cover."),
                ("Check", "Say what the model would do there if it only knew the list."),
            ],
            [
                _ask(rng, "Where does this kind of model fail?", "In a situation missing from its examples.", ["In the first example it memorized.", "Only when the task has no name."]),
                _ask(rng, "Sounding sure is not the same as…", "Being right.", ["Having seen an example.", "Producing an answer."]),
                _ask(rng, "The missing situation is useful because…", "It shows where confidence is not evidence.", ["It should be deleted from the task.", "It proves the model knows the world."]),
            ],
        ),
        _lesson(
            "What you would add",
            15,
            [
                ("Concept", "A better set of examples includes the missing situation, labeled so the pattern can include it."),
                ("Try", "Write the example you would add, in one line."),
                ("Check", "Check that it is not already one of the three kinds."),
            ],
            [
                _ask(rng, "You improve the examples by…", "Adding the missing situation.", ["Adding another copy of the first kind.", "Removing every hard case."]),
                _ask(rng, "The added example should be…", "Different from the three kinds you listed.", ["A repeat of the easiest kind.", "Unlabeled, so the model can guess."]),
                _ask(rng, "After you add it, the model can…", "Learn a pattern that includes that situation.", ["Know every future case.", "Skip training."]),
            ],
        ),
    ]


def _systems(title: str, focus: str, rng: random.Random) -> list[dict]:
    return [
        _lesson(
            "The narrowest point",
            15,
            [
                ("Concept", f"In {title}, a system fails first at its narrowest point. Speeding up a wide step does not move the result. Your focus is {focus}."),
                ("Try", "Name the process in one line."),
                ("Check", "If you named a goal instead of a process, start again with the steps."),
            ],
            [
                _ask(rng, "A system fails first at…", "Its narrowest point.", ["Its widest step.", "The newest part."]),
                _ask(rng, "Speeding up a step nothing is waiting on…", "May not move the result.", ["Always doubles the result.", "Removes the constraint."]),
                _ask(rng, "Name first…", "The process, as steps.", ["The goal, with no steps.", "The tool you hope to buy."]),
            ],
        ),
        _lesson(
            "The step everything waits on",
            15,
            [
                ("Concept", "The constraint is the step the rest of the process waits on."),
                ("Try", f"In “{focus}”, write the single step everything else waits on."),
                ("Check", "Ask: if this step stopped, would the others stop too?"),
            ],
            [
                _ask(rng, "The constraint is…", "The step everything else waits on.", ["The step you did most recently.", "The step with the longest name."]),
                _ask(rng, "If that step stopped, the others…", "Would stop too.", ["Would finish faster.", "Would become the constraint automatically."]),
                _ask(rng, "You want…", "One step, not a list of wishes.", ["Every step marked as the constraint.", "A new tool before you name the step."]),
            ],
        ),
        _lesson(
            "A change that does not move the result",
            15,
            [
                ("Concept", "If you make a non-constraint twice as fast and the whole process is unchanged, you chose the wrong step."),
                ("Try", "Pick one step that is not the constraint and say what would happen if it were twice as fast."),
                ("Check", "The honest answer is often: nothing you can see."),
            ],
            [
                _ask(rng, "A wrong step, made twice as fast, usually…", "Leaves the whole process unchanged.", ["Doubles the result.", "Becomes the constraint by effort."]),
                _ask(rng, "That outcome tells you…", "You did not choose the constraint.", ["The system is finished.", "Speed no longer matters."]),
                _ask(rng, "The test compares…", "The whole result, before and after.", ["How busy the step looks.", "How new the tool is."]),
            ],
        ),
        _lesson(
            "One change, then measure",
            15,
            [
                ("Concept", "Change only the constraint, then measure the whole result again. A second change before you measure hides which one worked."),
                ("Try", "Write the one change, and the number you will look at afterward."),
                ("Check", "If you listed two changes, cross one out."),
            ],
            [
                _ask(rng, "How many changes do you make before measuring?", "One, on the constraint.", ["Every slow step at once.", "None. Measuring comes first and last with no change."]),
                _ask(rng, "Two changes before a measurement…", "Hide which one worked.", ["Are the fastest way to learn.", "Are required for a fair test."]),
                _ask(rng, "After the change you look at…", "The whole result.", ["Only the step you touched.", "A different process."]),
            ],
        ),
    ]


def _general(title: str, focus: str, rng: random.Random) -> list[dict]:
    subject = title.strip() or "this course"
    return [
        _lesson(
            f"Say what {subject} is",
            15,
            [
                ("Concept", f"{subject} starts with one sentence a newcomer could repeat. The sentence should carry {focus}, and nothing else."),
                ("Try", f"Write: “{subject} means …” and finish it with {focus}."),
                ("Check", "Read it to someone who has not seen the course. If they ask what you meant, the sentence is still two ideas."),
            ],
            [
                _ask(rng, f"The first sentence about {subject} should carry…", focus, ["Every term you might need later.", "A project too big to finish today."]),
                _ask(rng, "A sentence is finished when…", "A newcomer could repeat it.", ["It uses the longest words you know.", "It mentions a second topic."]),
                _ask(rng, "If the listener asks what you meant…", "The sentence still holds two ideas.", ["The course is too advanced.", "You should add more topics."]),
            ],
        ),
        _lesson(
            "Try the smallest version",
            15,
            [
                ("Concept", f"The smallest version of {subject} is one example you can finish today, aimed at {focus}."),
                ("Try", "Do that example once, with something from your own work."),
                ("Check", "If you cannot point at the finished example, you planned instead of trying."),
            ],
            [
                _ask(rng, "The right size for a first try is…", "One example you can finish today.", ["A full project.", "A reread of the definition."]),
                _ask(rng, "The example should aim at…", focus, ["A different skill you already know.", "As many cases as possible."]),
                _ask(rng, "You tried it when you can…", "Point at the finished example.", ["Describe the example you meant to do.", "Highlight the lesson title."]),
            ],
        ),
        _lesson(
            "Find the part that slips",
            15,
            [
                ("Concept", f"Close the notes and explain {focus} again. The word you cannot say is the next thing to study."),
                ("Try", "Explain it aloud without looking. Mark the missing word."),
                ("Check", "That word, not the whole topic, is the gap."),
            ],
            [
                _ask(rng, "The gap is…", "The word you cannot say.", ["The entire subject.", "The part you already explained easily."]),
                _ask(rng, "You find it by…", "Explaining without the notes.", ["Rereading the title.", "Adding more examples before you speak."]),
                _ask(rng, f"In this course the explanation should come back to…", focus, ["A new topic.", "The history of the field."]),
            ],
        ),
        _lesson(
            "Teach it back",
            15,
            [
                ("Concept", f"Teach {subject} in three lines: the sentence, the example, and the word that slipped. That is the whole of {focus} for today."),
                ("Try", "Write those three lines and stop."),
                ("Check", "If a line does not serve the focus, cut it."),
            ],
            [
                _ask(rng, "The three lines are…", "The sentence, the example, and the word that slipped.", ["Three new topics.", "The same sentence three times."]),
                _ask(rng, "A line that does not serve the focus…", "Should be cut.", ["Should be expanded.", "Is the most important line."]),
                _ask(rng, f"Today’s version of {subject} is done when…", f"Those three lines cover {focus}.", ["You have outlined a longer course.", "You can name ten related ideas."]),
            ],
        ),
    ]
