import React, { useState } from 'react';
import AuthLayout from './AuthLayout';
import LoginView from './LoginView';
import ForgotPasswordView from './ForgotPasswordView';
import VerifyOtpView from './VerifyOtpView';
import ResetPasswordView from './ResetPasswordView';

export default function AuthFlowContainer({ onLoginSuccess, initialTab = 'login' }) {
  const [currentTab, setCurrentTab] = useState(initialTab);

  return (
    <AuthLayout>
      {currentTab === 'login' && (
        <LoginView onLoginSuccess={onLoginSuccess} onSwitchTab={(tab) => setCurrentTab(tab)} />
      )}

      {currentTab === 'forgot' && <ForgotPasswordView onSwitchTab={(tab) => setCurrentTab(tab)} />}

      {currentTab === 'otp' && (
        <VerifyOtpView
          onSwitchTab={(tab) => setCurrentTab(tab)}
          onVerifySuccess={() => setCurrentTab('reset-password')}
        />
      )}

      {currentTab === 'reset-password' && <ResetPasswordView onSwitchTab={(tab) => setCurrentTab(tab)} />}
    </AuthLayout>
  );
}
