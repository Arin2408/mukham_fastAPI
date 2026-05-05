from organisation.models import CustomUser
from collections import defaultdict

def cleanup_and_normalize():
    users = CustomUser.objects.all()
    normalized_map = defaultdict(list)
    
    # Identify groups of duplicates based on last 10 digits
    for u in users:
        base = ''.join(filter(str.isdigit, u.mobile_number))[-10:]
        normalized_map[base].append(u)
    
    for base, group in normalized_map.items():
        if len(group) > 1:
            # Sort: Organizations first, then by ID
            group.sort(key=lambda x: (not x.is_organization, x.org_id))
            to_keep = group[0]
            to_delete = group[1:]
            for d in to_delete:
                print(f"Deleting duplicate: {d.name} ({d.mobile_number}) ID: {d.org_id} (Keeping: {to_keep.name})")
                d.delete()
    
    # Normalize remaining users
    for u in CustomUser.objects.all():
        base = ''.join(filter(str.isdigit, u.mobile_number))[-10:]
        if u.mobile_number != base:
            print(f"Normalizing {u.mobile_number} -> {base}")
            u.mobile_number = base
            u.save()

if __name__ == "__main__":
    cleanup_and_normalize()
