import { Pencil, Image, Film, Music, Mic, FileText } from "lucide-react";

const createOptions = [
  { name: "Image", desc: "Generate AI images with SDXL, Flux, or SD 1.5", icon: Image, color: "bg-purple-600" },
  { name: "Video", desc: "Create videos with WAN 2.1 text-to-video", icon: Film, color: "bg-blue-600" },
  { name: "Voice", desc: "Generate speech with ElevenLabs or XTTS", icon: Mic, color: "bg-green-600" },
  { name: "Music", desc: "AI music generation for soundtracks", icon: Music, color: "bg-amber-600" },
  { name: "Commercial", desc: "Full production pipeline — image + video + voice", icon: FileText, color: "bg-pink-600" },
];

export default function CreatePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Create</h1>
        <p className="text-sm text-gray-500">Start a new creation — image, video, commercial, music, or podcast.</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {createOptions.map((opt) => (
          <button key={opt.name} className="group rounded-xl border border-white/[0.06] bg-[#12122a] p-6 text-left hover:border-purple-500/30 hover:bg-purple-600/5 transition-all">
            <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${opt.color} mb-4`}>
              <opt.icon className="h-6 w-6 text-white" />
            </div>
            <h3 className="text-lg font-semibold text-white group-hover:text-purple-300">{opt.name}</h3>
            <p className="mt-1 text-sm text-gray-500">{opt.desc}</p>
          </button>
        ))}
      </div>

      {/* Quick Generate */}
      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
        <h3 className="text-sm font-semibold text-white mb-3">Quick Generate</h3>
        <div className="flex gap-3">
          <input
            className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 placeholder:text-gray-600 outline-none focus:border-purple-500/50"
            placeholder="Describe what you want to create..."
          />
          <select className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 outline-none">
            <option>Flux Dev</option>
            <option>SDXL Turbo</option>
            <option>SD 1.5</option>
          </select>
          <button className="rounded-lg bg-purple-600 px-6 py-2 text-sm font-medium text-white hover:bg-purple-700">
            Generate
          </button>
        </div>
      </div>
    </div>
  );
}
