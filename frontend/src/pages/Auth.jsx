import { useState } from 'react';
import { ArrowRight, BookOpen, Brain, Eye, EyeOff, Globe2, Layers3, LoaderCircle, AlertCircle } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import './Auth.css';

export default function Auth({ mode }) {
  return <AuthScreen key={mode} mode={mode} />;
}

function AuthScreen({ mode }) {
  const navigate = useNavigate();
  const { authenticate } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const isRegister = mode === 'register';

  const submit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError('');
    try {
      await authenticate(isRegister ? 'register' : 'login', { email: email.trim(), password });
      navigate('/chat', { replace: true });
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="auth-studio">
      <aside className="auth-story" aria-label="About ResearchAgent">
        <div className="auth-wordmark"><span><Brain size={22} /></span>ResearchAgent</div>
        <div className="auth-story-content">
          <span className="auth-overline">A WORKSPACE FOR CURIOUS MINDS</span>
          <h2>Follow a question.<br /><em>Find a new<br />perspective.</em></h2>
          <p>Turn your curiosity into thoughtful research.<br />Explore the evidence. Connect the ideas.<br />Keep what matters.</p>
          <div className="auth-art" aria-hidden="true">
            <div className="auth-art-orbit" />
            <div className="auth-paper auth-paper-back" />
            <div className="auth-paper auth-paper-front">
              <div className="auth-paper-label"><BookOpen size={15} /> THE RESEARCH NOTEBOOK</div>
              <span className="auth-paper-title">A little clarity,<br /><em>one question at a time.</em></span>
              <div className="auth-paper-rule" /><div className="auth-paper-line" /><div className="auth-paper-line short" />
              <div className="auth-paper-footer"><span className="auth-paper-dot" /> Ideas worth coming back to <ArrowRight size={14} /></div>
            </div>
            <span className="auth-art-seal"><Globe2 size={26} /></span>
          </div>
        </div>
        <div className="auth-story-footer"><span><Globe2 size={14} /> Explore</span><span><Layers3 size={14} /> Connect</span><span><BookOpen size={14} /> Discover</span></div>
      </aside>

      <section className="auth-entry" aria-labelledby="auth-heading">
        <div className="auth-entry-top"><span>Your next discovery starts here.</span><span className="auth-entry-mark"><Brain size={19} /> ResearchAgent</span></div>
        <div className="auth-entry-body">
          <div className="auth-form-intro">
            <span className="auth-overline">{isRegister ? 'MAKE ROOM FOR NEW IDEAS' : 'YOUR RESEARCH, CONTINUED'}</span>
            <h1 id="auth-heading">{isRegister ? <>A fresh start.<br /><em>A curious mind.</em></> : <>Welcome<br /><em>back.</em></>}</h1>
            <p>{isRegister ? 'Create an account and make space for your next discovery.' : 'Settle in. Your next good question is waiting.'}</p>
          </div>

          <form className="auth-studio-form" onSubmit={submit} aria-busy={submitting}>
            <div className="auth-field">
              <label htmlFor="auth-email">Email address</label>
              <input id="auth-email" name="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" autoCapitalize="none" spellCheck={false} placeholder="you@example.com" disabled={submitting} required />
            </div>
            <div className="auth-field">
              <label htmlFor="auth-password">Password</label>
              <div className="auth-password-wrap">
                <input id="auth-password" name="password" type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={isRegister ? 'new-password' : 'current-password'} minLength={8} placeholder={isRegister ? 'Create a password' : 'Enter your password'} disabled={submitting} aria-describedby={isRegister ? 'auth-password-help' : undefined} required />
                <button type="button" className="auth-password-toggle" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} disabled={submitting}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button>
              </div>
              {isRegister && <p id="auth-password-help" className="auth-field-help">Use at least 8 characters.</p>}
            </div>
            {error && <div className="auth-studio-error" role="alert"><AlertCircle size={17} /><p>{error}</p></div>}
            <button className="auth-studio-submit" disabled={submitting} type="submit">
              {submitting ? <><LoaderCircle size={17} className="auth-loading-icon" />{isRegister ? 'Creating your account…' : 'Signing you in…'}</> : <>{isRegister ? 'Create your workspace' : 'Sign in to your workspace'}<ArrowRight size={17} /></>}
            </button>
          </form>
          <div className="auth-entry-switch">{isRegister ? 'Already have an account?' : 'New to ResearchAgent?'}{' '}{submitting ? <span>{isRegister ? 'Sign in' : 'Create an account'}</span> : <Link to={isRegister ? '/login' : '/register'}>{isRegister ? 'Sign in' : 'Create an account'}<ArrowRight size={13} /></Link>}</div>
        </div>
        <footer className="auth-entry-footer"><span>Research with intention.</span><span>Stay curious.</span></footer>
      </section>
    </main>
  );
}
