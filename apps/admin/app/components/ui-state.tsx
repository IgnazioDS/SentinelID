import type { ReactNode } from 'react';

export function LoadingState({ text = 'Loading...' }: { text?: string }) {
  return <div className="state state-loading">{text}</div>;
}

export function ErrorState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="state state-error">
      <p>{message}</p>
      {action}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="state state-empty">
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
    </div>
  );
}
