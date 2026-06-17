import '../styles/InfoToast.css';

interface InfoToastProps {
  message: string;
  tone: 'success' | 'error';
  onDismiss: () => void;
}

function InfoToast({ message, tone, onDismiss }: InfoToastProps) {
  return (
    <div className={`info-toast info-toast-${tone}`} onClick={onDismiss} role="status">
      <span>{message}</span>
    </div>
  );
}

export default InfoToast;
