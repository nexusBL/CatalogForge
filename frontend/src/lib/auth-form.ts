export const USERNAME_MIN = 3;
export const USERNAME_MAX = 30;

export function validateUsername(username: string): string | null {
  const value = username.trim();
  if (!value) {
    return "Username is required.";
  }
  if (value.length < USERNAME_MIN) {
    return "Username must be at least 3 characters.";
  }
  if (value.length > USERNAME_MAX) {
    return "Username must be at most 30 characters.";
  }
  return null;
}

export function validateSignupPasswords(password: string, confirmPassword: string): string | null {
  if (!password) {
    return "Password is required.";
  }
  if (password.length < 8) {
    return "Password must be at least 8 characters.";
  }
  if (password !== confirmPassword) {
    return "Passwords do not match.";
  }
  return null;
}

export function validateChangePassword(
  currentPassword: string,
  newPassword: string,
  confirmPassword: string,
): string | null {
  if (!currentPassword) {
    return "Current password is required.";
  }
  return validateSignupPasswords(newPassword, confirmPassword);
}

export function changePasswordErrorMessage(message: string | undefined, fallback: string): string {
  if (!message) {
    return fallback;
  }
  if (/invalid password/i.test(message)) {
    return "Current password is incorrect.";
  }
  if (/too short/i.test(message)) {
    return "Password must be at least 8 characters.";
  }
  return message;
}

export function authErrorMessage(message: string | undefined, fallback: string): string {
  if (!message) {
    return fallback;
  }
  if (/already taken|already exists|username is already/i.test(message)) {
    return "That username is already taken. Please try another.";
  }
  if (/invalid username or password/i.test(message)) {
    return "Invalid username or password.";
  }
  return message;
}
