import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type StatCardProps = {
  title: string;
  value: React.ReactNode;
  hint?: string;
  valueClassName?: string;
};

export function StatCard({ title, value, hint, valueClassName }: StatCardProps) {
  return (
    <Card className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-neon/6 via-transparent to-accent/12" />
      <div className="pointer-events-none absolute left-0 top-0 h-[2px] w-16 bg-neon/70" />
      <CardHeader>
        <CardTitle className="text-[10px] uppercase tracking-[0.3em] text-slate-500">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="relative">
        <div
          className={cn(
            "text-2xl font-semibold text-slate-100 tabular",
            valueClassName
          )}
        >
          {value}
        </div>
        {hint ? <div className="text-xs text-slate-500 mt-2">{hint}</div> : null}
      </CardContent>
    </Card>
  );
}
