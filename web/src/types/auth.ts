export interface UserProfile {
  id: string;
  username: string;
  email: string;
  display_name: string;
  full_name?: string; // alias kept for compatibility
  role: string;
  tenant_id: string;
  status: string;
  actor_type?: string;
  is_active?: boolean;
}
