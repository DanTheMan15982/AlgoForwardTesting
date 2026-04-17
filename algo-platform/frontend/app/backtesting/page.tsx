import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function BacktestingPage() {
  return (
    <div className="space-y-6">
      <section>
        <p className="text-xs uppercase tracking-[0.35em] text-neonSoft">Backtesting</p>
        <h2 className="text-2xl font-semibold text-slate-100">Coming Soon</h2>
      </section>
      <Card>
        <CardHeader>
          <CardTitle>Backtesting Workspace</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-400">
          This area is reserved for backtesting tools.
        </CardContent>
      </Card>
    </div>
  );
}
