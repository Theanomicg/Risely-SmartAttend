function SectionCard({ title, children, action }) {
  return (
    <section className="rounded-3xl border border-white/70 bg-white/70 p-6 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur">
      <div className="mb-5 flex items-center justify-between gap-4">
        <h2 className="font-display text-2xl text-ink">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export default SectionCard;
