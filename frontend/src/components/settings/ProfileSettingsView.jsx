import React, { useState, useEffect } from 'react';
import {
  User,
  Lock,
  Mail,
  Phone,
  Save,
  Key,
  Shield,
  Check,
  Eye,
  EyeOff,
  GitBranch,
  ShieldCheck,
  ToggleLeft,
  ToggleRight,
  Calendar,
  UserCheck,
} from 'lucide-react';
import { profileApi } from '../../services/api';

const APP_VERSION = 'v4.19.01';

export default function ProfileSettingsView({ addToast, currentUser }) {
  const [loading, setLoading] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);

  // Form states
  const [profileData, setProfileData] = useState({
    first_name: '',
    last_name: '',
    username: '',
    email: '',
    phone: '',
    date_joined: '',
  });

  const [passwordData, setPasswordData] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  });

  // Password visibility toggles
  const [showCurrentPw, setShowCurrentPw] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);
  const [showConfirmPw, setShowConfirmPw] = useState(false);

  // Security preferences
  const [twoFactor, setTwoFactor] = useState(false);
  const [loginNotify, setLoginNotify] = useState(true);
  const [sessionTimeout, setSessionTimeout] = useState('10080');
  const [superMode, setSuperMode] = useState(false);

  useEffect(() => {
    async function fetchProfile() {
      setLoading(true);
      try {
        const res = await profileApi.getProfile();
        if (res.user || res.data || res.success) {
          const u = res.user || res.data || res;
          setProfileData({
            first_name: u.first_name || '',
            last_name: u.last_name || '',
            username: u.username || '',
            email: u.email || '',
            phone: u.phone || '',
            date_joined: u.date_joined || u.created_at || '',
          });
        }
      } catch (err) {
        if (currentUser) {
          setProfileData({
            first_name: currentUser.first_name || '',
            last_name: currentUser.last_name || '',
            username: currentUser.username || '',
            email: currentUser.email || '',
            phone: currentUser.phone || '',
            date_joined: currentUser.date_joined || '',
          });
        }
      } finally {
        setLoading(false);
      }
    }
    fetchProfile();
  }, [currentUser]);

  const handleProfileSubmit = async (e) => {
    e.preventDefault();
    setSavingProfile(true);
    try {
      const res = await profileApi.updateProfile(profileData);
      if (res.success !== false) {
        addToast?.('Profile details updated successfully!', 'success');
      } else {
        addToast?.(res.message || res.error || 'Failed to update profile', 'error');
      }
    } catch (err) {
      addToast?.('Error updating profile', 'error');
    } finally {
      setSavingProfile(false);
    }
  };

  const handlePasswordSubmit = async (e) => {
    e.preventDefault();
    if (passwordData.newPassword !== passwordData.confirmPassword) {
      addToast?.('New password and confirm password do not match', 'warning');
      return;
    }
    if (passwordData.newPassword.length < 6) {
      addToast?.('New password must be at least 6 characters', 'warning');
      return;
    }
    setSavingPassword(true);
    try {
      const res = await profileApi.changePassword({
        old_password: passwordData.currentPassword,
        new_password: passwordData.newPassword,
      });
      if (res.success !== false) {
        addToast?.('Password changed successfully!', 'success');
        setPasswordData({ currentPassword: '', newPassword: '', confirmPassword: '' });
      } else {
        addToast?.(res.message || res.error || 'Failed to change password', 'error');
      }
    } catch (err) {
      addToast?.('Error changing password', 'error');
    } finally {
      setSavingPassword(false);
    }
  };

  const displayName = profileData.first_name
    ? `${profileData.first_name} ${profileData.last_name || ''}`.trim()
    : profileData.username || 'System Admin';

  const initials = displayName.slice(0, 2).toUpperCase();

  if (loading) {
    return (
      <div style={{ padding: '0', height: '100%', width: '100%' }}>
        <div className="skeleton" style={{ height: '100%', width: '100%', borderRadius: 0 }} />
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: '100%', padding: 0, margin: 0, background: '#ffffff', overflow: 'hidden' }}>
      {/* ── Seamless Full-Viewport 0-Gap Unified Panel Flush to Edges ── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 300px',
          gap: 0,
          width: '100%',
          height: '100%',
          background: '#ffffff',
          border: 'none',
          borderRadius: 0,
          overflow: 'hidden',
        }}
      >
        {/* ── LEFT COLUMN: Stacked Settings Sections (Divided by Border-Bottom, 0 Gaps) ── */}
        <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', borderRight: '1px solid #e2e8f0' }}>
          {/* Section 1: Profile Information */}
          <div style={{ borderBottom: '1px solid #e2e8f0', padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '8px',
                  background: '#eff6ff',
                  color: 'rgb(0, 80, 210)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <User size={18} />
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>Profile Information</h3>
                <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#64748b' }}>Update your personal details</p>
              </div>
            </div>

            <form onSubmit={handleProfileSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '12px',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '6px',
                    }}
                  >
                    First Name
                  </label>
                  <input
                    type="text"
                    value={profileData.first_name}
                    onChange={(e) => setProfileData({ ...profileData, first_name: e.target.value })}
                    placeholder="Enter first name"
                    style={{
                      width: '100%',
                      height: '36px',
                      padding: '0 12px',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      fontSize: '13px',
                      outline: 'none',
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '12px',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '6px',
                    }}
                  >
                    Last Name
                  </label>
                  <input
                    type="text"
                    value={profileData.last_name}
                    onChange={(e) => setProfileData({ ...profileData, last_name: e.target.value })}
                    placeholder="Enter last name"
                    style={{
                      width: '100%',
                      height: '36px',
                      padding: '0 12px',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      fontSize: '13px',
                      outline: 'none',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '12px',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '6px',
                    }}
                  >
                    Username
                  </label>
                  <input
                    type="text"
                    value={profileData.username}
                    onChange={(e) => setProfileData({ ...profileData, username: e.target.value })}
                    placeholder="Enter username"
                    style={{
                      width: '100%',
                      height: '36px',
                      padding: '0 12px',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      fontSize: '13px',
                      outline: 'none',
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '12px',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '6px',
                    }}
                  >
                    Email Address
                  </label>
                  <input
                    type="email"
                    value={profileData.email}
                    onChange={(e) => setProfileData({ ...profileData, email: e.target.value })}
                    placeholder="Enter email"
                    style={{
                      width: '100%',
                      height: '36px',
                      padding: '0 12px',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      fontSize: '13px',
                      outline: 'none',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '12px',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '6px',
                    }}
                  >
                    Phone Number
                  </label>
                  <input
                    type="tel"
                    value={profileData.phone}
                    onChange={(e) => setProfileData({ ...profileData, phone: e.target.value })}
                    placeholder="Enter phone number"
                    style={{
                      width: '100%',
                      height: '36px',
                      padding: '0 12px',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      fontSize: '13px',
                      outline: 'none',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: '4px' }}>
                <button
                  type="submit"
                  disabled={savingProfile}
                  style={{
                    background: 'linear-gradient(135deg, rgb(0, 80, 210) 0%, rgb(0, 180, 255) 100%)',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '6px',
                    padding: '8px 20px',
                    fontSize: '13px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    boxShadow: '0 2px 6px rgba(0, 80, 210, 0.2)',
                  }}
                >
                  <Check size={14} /> {savingProfile ? 'Saving…' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>

          {/* Section 2: Change Password */}
          <div style={{ borderBottom: '1px solid #e2e8f0', padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '8px',
                  background: '#fef3c7',
                  color: '#d97706',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Lock size={18} />
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>Change Password</h3>
                <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#64748b' }}>
                  Update your password to keep your account secure
                </p>
              </div>
            </div>

            <form onSubmit={handlePasswordSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label
                  style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}
                >
                  Current Password
                </label>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <input
                    type={showCurrentPw ? 'text' : 'password'}
                    required
                    value={passwordData.currentPassword}
                    onChange={(e) => setPasswordData({ ...passwordData, currentPassword: e.target.value })}
                    placeholder="Enter current password"
                    style={{
                      width: '100%',
                      height: '36px',
                      padding: '0 38px 0 12px',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      fontSize: '13px',
                      outline: 'none',
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowCurrentPw(!showCurrentPw)}
                    style={{
                      position: 'absolute',
                      right: '10px',
                      background: 'none',
                      border: 'none',
                      color: '#94a3b8',
                      cursor: 'pointer',
                    }}
                  >
                    {showCurrentPw ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '12px',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '6px',
                    }}
                  >
                    New Password
                  </label>
                  <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                    <input
                      type={showNewPw ? 'text' : 'password'}
                      required
                      value={passwordData.newPassword}
                      onChange={(e) => setPasswordData({ ...passwordData, newPassword: e.target.value })}
                      placeholder="Enter new password"
                      style={{
                        width: '100%',
                        height: '36px',
                        padding: '0 38px 0 12px',
                        border: '1px solid #cbd5e1',
                        borderRadius: '6px',
                        fontSize: '13px',
                        outline: 'none',
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowNewPw(!showNewPw)}
                      style={{
                        position: 'absolute',
                        right: '10px',
                        background: 'none',
                        border: 'none',
                        color: '#94a3b8',
                        cursor: 'pointer',
                      }}
                    >
                      {showNewPw ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </div>

                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '12px',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '6px',
                    }}
                  >
                    Confirm New Password
                  </label>
                  <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                    <input
                      type={showConfirmPw ? 'text' : 'password'}
                      required
                      value={passwordData.confirmPassword}
                      onChange={(e) => setPasswordData({ ...passwordData, confirmPassword: e.target.value })}
                      placeholder="Confirm new password"
                      style={{
                        width: '100%',
                        height: '36px',
                        padding: '0 38px 0 12px',
                        border: '1px solid #cbd5e1',
                        borderRadius: '6px',
                        fontSize: '13px',
                        outline: 'none',
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPw(!showConfirmPw)}
                      style={{
                        position: 'absolute',
                        right: '10px',
                        background: 'none',
                        border: 'none',
                        color: '#94a3b8',
                        cursor: 'pointer',
                      }}
                    >
                      {showConfirmPw ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: '4px' }}>
                <button
                  type="submit"
                  disabled={savingPassword}
                  style={{
                    background: '#2563eb',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '6px',
                    padding: '8px 20px',
                    fontSize: '13px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    boxShadow: '0 2px 6px rgba(37, 99, 235, 0.2)',
                  }}
                >
                  <Key size={14} /> {savingPassword ? 'Updating…' : 'Update Password'}
                </button>
              </div>
            </form>
          </div>

          {/* Section 3: Security Settings */}
          <div style={{ padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '8px',
                  background: '#ecfdf5',
                  color: '#059669',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Shield size={18} />
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>Security Settings</h3>
                <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#64748b' }}>
                  Manage your account security preferences
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingBottom: '12px',
                  borderBottom: '1px solid #f1f5f9',
                }}
              >
                <div>
                  <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: '#0f172a' }}>
                    Two-Factor Authentication
                  </h4>
                  <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#64748b' }}>
                    Add an extra layer of security to your account
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={twoFactor}
                  onChange={(e) => setTwoFactor(e.target.checked)}
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                />
              </div>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingBottom: '12px',
                  borderBottom: '1px solid #f1f5f9',
                }}
              >
                <div>
                  <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: '#0f172a' }}>
                    Login Notifications
                  </h4>
                  <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#64748b' }}>
                    Get notified when someone logs into your account
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={loginNotify}
                  onChange={(e) => setLoginNotify(e.target.checked)}
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: '#0f172a' }}>Session Timeout</h4>
                  <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#64748b' }}>
                    Automatically logout after inactivity
                  </p>
                </div>
                <select
                  value={sessionTimeout}
                  onChange={(e) => setSessionTimeout(e.target.value)}
                  style={{
                    height: '36px',
                    padding: '0 12px',
                    border: '1px solid #cbd5e1',
                    borderRadius: '6px',
                    fontSize: '13px',
                    color: '#334155',
                    outline: 'none',
                  }}
                >
                  <option value="1440">1 day</option>
                  <option value="2880">2 days</option>
                  <option value="10080">7 days (default)</option>
                  <option value="21600">15 days</option>
                  <option value="43200">30 days</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* ── RIGHT COLUMN: Profile Card (300px Fixed, Flush to Right Edge, 0 Gaps) ── */}
        <div
          style={{
            width: '300px',
            height: '100%',
            overflowY: 'auto',
            background: '#ffffff',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Top Gradient Banner & Avatar */}
          <div
            style={{
              background: 'linear-gradient(135deg, rgb(0, 80, 210) 0%, rgb(0, 180, 255) 100%)',
              padding: '28px 20px 24px',
              display: 'flex',
              justifyContent: 'center',
            }}
          >
            <div
              style={{
                width: '76px',
                height: '76px',
                borderRadius: '16px',
                border: '3px solid rgba(255, 255, 255, 0.8)',
                boxShadow: '0 6px 16px rgba(0,0,0,0.18)',
                background: '#ffffff',
                color: 'rgb(0, 80, 210)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '26px',
                fontWeight: 800,
              }}
            >
              {initials}
            </div>
          </div>

          {/* Profile Info */}
          <div style={{ textAlign: 'center', padding: '20px 16px 16px' }}>
            <h3 style={{ margin: '0 0 6px', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>{displayName}</h3>
            <span
              style={{
                display: 'inline-block',
                background: 'linear-gradient(135deg, rgb(0, 80, 210) 0%, #7c3aed 100%)',
                color: '#ffffff',
                padding: '3px 12px',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
                marginBottom: '12px',
              }}
            >
              Administrator
            </span>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                color: '#64748b',
                fontSize: '12px',
              }}
            >
              <Mail size={12} style={{ color: 'rgb(0, 80, 210)' }} />
              <span>{profileData.email || 'admin@adarsh.com'}</span>
            </div>
          </div>

          {/* Stats Row: Member Since & Version */}
          <div style={{ borderTop: '1px solid #e2e8f0', borderBottom: '1px solid #e2e8f0', display: 'flex' }}>
            <div style={{ flex: 1, textAlign: 'center', padding: '12px 6px', borderRight: '1px solid #e2e8f0' }}>
              <span style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#0f172a' }}>
                {profileData.date_joined
                  ? new Date(profileData.date_joined).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
                  : 'Jan 2024'}
              </span>
              <span style={{ fontSize: '10px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
                Member Since
              </span>
            </div>

            <div style={{ flex: 1, textAlign: 'center', padding: '12px 6px' }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '12px',
                  fontWeight: 700,
                  color: '#1e40af',
                }}
              >
                <GitBranch size={11} /> {APP_VERSION}
              </span>
              <span
                style={{
                  display: 'block',
                  fontSize: '10px',
                  color: '#3b82f6',
                  textTransform: 'uppercase',
                  fontWeight: 600,
                }}
              >
                App Version
              </span>
            </div>
          </div>

          {/* Super Mode Action */}
          <div style={{ padding: '16px', marginTop: 'auto' }}>
            <button
              type="button"
              onClick={() => {
                setSuperMode(!superMode);
                addToast?.(superMode ? 'Super Mode deactivated' : 'Super Mode activated', 'info');
              }}
              style={{
                width: '100%',
                padding: '10px 14px',
                borderRadius: '8px',
                border: superMode ? '1px solid #16a34a' : '1px solid #e2e8f0',
                background: superMode ? '#f0fdf4' : '#f8fafc',
                color: superMode ? '#15803d' : '#475569',
                fontSize: '12px',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: 'pointer',
                fontFamily: 'var(--font-family)',
                transition: 'all 0.15s',
              }}
            >
              <span>Turn On Super Mode</span>
              {superMode ? (
                <ToggleRight size={18} style={{ color: '#16a34a' }} />
              ) : (
                <ToggleLeft size={18} style={{ color: '#94a3b8' }} />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
