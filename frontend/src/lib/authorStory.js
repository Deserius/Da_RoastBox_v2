// The words below are also the scripts for the bundled, page-by-page narration.
// Artwork and audio are static assets: opening the book never calls an AI API.
const asset = (path) => `${process.env.PUBLIC_URL || ""}/assets/about-author/${path}`;

export const AUTHOR_COVER_ART = asset("character.webp");

const chapters = [
  {
    title: "The Kid Who Asked Why",
    eyebrow: "It started with a question",
    alt: "A curious young Deserius discovers a glowing vintage computer among electronics and sketches.",
    sentences: [
      "Before the tattoos, before the cosmic detour, there was a kid staring at a computer like it owed him an explanation.",
      "I wanted to know how everything worked.",
      "Eventually, I discovered you could tell a machine what to do, and sometimes it would actually listen.",
    ],
  },
  {
    title: "The QBasic Incident",
    eyebrow: "A very retro superpower",
    alt: "Young Deserius experiments with code on an old CRT computer in a room full of floppy disks and notes.",
    sentences: [
      "By the late nineties, I was experimenting with QBasic.",
      "A few lines on a screen could make something happen, which felt like discovering a secret door.",
      "My first conversation with a computer was mostly me asking questions and the computer informing me I had made a syntax error.",
    ],
  },
  {
    title: "An Unexpected Creative Detour",
    eyebrow: "A different kind of code",
    alt: "Deserius works in a richly detailed art studio with sketches, airbrush tools and tattoo equipment.",
    sentences: [
      "Somewhere along the way, my curiosity picked up a pencil, an airbrush, and a tattoo machine.",
      "What began as a fascination with how things work became a love of making things that mean something.",
      "Turns out code and art have one thing in common: both start with a stubborn idea.",
    ],
  },
  {
    title: "Ink, Mountains & Mastery",
    eyebrow: "An artist out of Colorado",
    alt: "The artist stands in his Colorado studio amid finished artwork, with mountains beyond the window.",
    sentences: [
      "Over roughly fifteen years, I developed my craft in drawing, airbrushing, design, and tattooing, eventually becoming an award winning artist out of Colorado.",
      "There were long hours, a lot of ink, and enough creative experiments to convince me that imagination is not a hobby.",
      "It's a survival skill.",
    ],
  },
  {
    title: "The Cosmic Interruption",
    eyebrow: "Well, this is unexpected",
    alt: "A puzzled Deserius encounters a glowing spacecraft and curious extraterrestrial visitors.",
    sentences: [
      "Now, about that cosmic detour.",
      "My version of the story involves extraterrestrial visitors, a spacecraft, and a trip to an alternate world.",
      "I know how that sounds.",
      "Trust me, I was there, and I still have questions.",
      "Apparently, the universe does not believe in ordinary career paths.",
    ],
  },
  {
    title: "The Other Side of Reality",
    eyebrow: "A world almost like ours",
    alt: "Deserius creates artwork in an otherworldly studio beneath a strange, luminous sky.",
    sentences: [
      "That other world looked a lot like this one, except the rules of reality seemed to be written in a different font.",
      "In my story, I found art, tattooing, design, and entrepreneurship there.",
      "Whether you're following the timeline or just enjoying the ride, welcome to my particular corner of the multiverse.",
    ],
  },
  {
    title: "Return to a Different World",
    eyebrow: "Reality installed an update",
    alt: "Deserius looks bemused at a modern city full of unfamiliar screens, phones and technology.",
    sentences: [
      "About five years ago, I found my way back here, and the place had upgraded while I was away.",
      "Technology had changed, the internet had changed, and apparently everyone had agreed to update the operating system of reality without sending me the release notes.",
      "Familiar planet.",
      "Very confusing onboarding.",
    ],
  },
  {
    title: "Speaking Machine Again",
    eyebrow: "A second beginning",
    alt: "Deserius returns to programming at a modern workstation surrounded by art and creative tools.",
    sentences: [
      "So I sat down with the machines again.",
      "Programming, artificial intelligence, design, and creative tools became part of the same conversation.",
      "I wasn't starting over so much as introducing the artist I'd become to the curious kid who still wanted to know what every button did.",
    ],
  },
  {
    title: "The Squirrel Conspiracy",
    eyebrow: "Give them their flowers. And acorns.",
    alt: "Deserius meets a charming council of squirrels, including one with a tiny computer.",
    sentences: [
      "And then there are the squirrels.",
      "My spirit animals, my furry little philosophers, and possibly the only creatures who actually read the universe's user manual.",
      "Give a squirrel an acorn, a tiny computer, and five minutes, and I suspect it could explain more than most meetings.",
    ],
  },
  {
    title: "Rewriting Reality",
    eyebrow: "The story continues",
    alt: "Deserius and a squirrel in a hopeful universe where artwork and digital technology come together.",
    sentences: [
      "Now I bring art, technology, and imagination together to build things that might make this world a little better.",
      "First, my deepest thanks to God.",
      "Then my mama, the people I hold dear, and all the different AI solutions and ChatGPTs that helped create this app.",
      "Da RoastBox was created by me, Deserius Arte, under the Hustler Anomalies Enterprises LLC brand.",
      "This is just the beginning.",
    ],
  },
];

export const AUTHOR_CHAPTERS = chapters.map((chapter, index) => {
  const number = String(index + 1).padStart(2, "0");
  return { ...chapter, number, image: asset(`images/${number}.webp`), audio: asset(`audio/${number}.mp3`) };
});
