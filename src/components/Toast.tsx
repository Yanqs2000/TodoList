import '../styles/Toast.css';

interface ToastProps {
  icon: string;
  title: string;
  description: string;
  onDismiss: () => void;
}

function Toast({ icon, title, description, onDismiss }: ToastProps) {
  return (
    <div className="toast" onClick={onDismiss}>
      <span className="toast-icon">{icon}</span>
      <div className="toast-content">
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
    </div>
  );
}

export default Toast;
