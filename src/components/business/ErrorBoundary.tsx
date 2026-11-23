import { Component, type ReactNode } from "react";
import { Btn } from "@/components/ui";

interface Props {
  children: ReactNode;
  /** 变化时自动清除错误状态（用于路由切换后重新渲染新页面） */
  resetKey?: string;
  /** 内联模式：渲染在内容区，保留导航；默认 false 为整屏兜底 */
  inline?: boolean;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  private reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const detail = (
      <>
        <div className={`font-semibold text-ink-800 ${this.props.inline ? "text-[15px]" : "text-base"}`}>
          页面出错了
        </div>
        <div className="mt-2 break-all text-[12px] leading-5 text-ink-500">{error.message}</div>
        <div className="mt-3 flex justify-center gap-2">
          <Btn onClick={this.reset}>重试</Btn>
          <Btn v="ghost" onClick={() => window.location.reload()}>刷新页面</Btn>
        </div>
      </>
    );

    if (this.props.inline) {
      return (
        <section className="rounded-card border border-line bg-white px-6 py-10 text-center">
          {detail}
        </section>
      );
    }

    return (
      <div className="grid h-screen place-items-center bg-ink-100 p-6">
        <section className="w-[420px] rounded-lg border border-line bg-white p-6 text-center shadow-sm">
          {detail}
        </section>
      </div>
    );
  }
}
