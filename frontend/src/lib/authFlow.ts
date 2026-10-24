export function requiresPasswordChange(user: {
  must_change_password: boolean;
}): boolean {
  return user.must_change_password;
}

export function passwordChangeError(
  currentPassword: string,
  newPassword: string,
): string {
  if (newPassword.length < 12) {
    return "新密码至少需要 12 个字符";
  }
  if (newPassword === currentPassword) {
    return "新密码不能与当前密码相同";
  }
  return "";
}
