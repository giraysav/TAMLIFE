export function EmptyState({ label = "Kayit yok" }: { label?: string }) {
  return <p className="text-sm text-muted-foreground">{label}</p>
}
