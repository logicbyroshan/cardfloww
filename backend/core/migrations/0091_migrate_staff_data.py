from django.db import migrations

def migrate_staff_to_new_models(apps, schema_editor):
    Staff = apps.get_model('core', 'Staff')
    Operator = apps.get_model('operators', 'Operator')
    Assistant = apps.get_model('assistants', 'Assistant')
    Photographer = apps.get_model('core', 'Photographer')

    db_alias = schema_editor.connection.alias

    for s in Staff.objects.using(db_alias).all():
        if s.staff_type == 'admin_staff':
            # Create Operator
            op = Operator.objects.using(db_alias).create(
                id=s.id,
                user=s.user,
                department=s.department,
                designation=s.designation,
                perm_idcard_client_list=s.perm_idcard_client_list,
                perm_manage_client_staff=s.perm_manage_client_staff,
                perm_idcard_setting_list=s.perm_idcard_setting_list,
                perm_idcard_setting_add=s.perm_idcard_setting_add,
                perm_idcard_setting_edit=s.perm_idcard_setting_edit,
                perm_idcard_setting_delete=s.perm_idcard_setting_delete,
                perm_idcard_setting_status=s.perm_idcard_setting_status,
                perm_idcard_pending_list=s.perm_idcard_pending_list,
                perm_idcard_verified_list=s.perm_idcard_verified_list,
                perm_idcard_pool_list=s.perm_idcard_pool_list,
                perm_idcard_approved_list=s.perm_idcard_approved_list,
                perm_idcard_download_list=s.perm_idcard_download_list,
                perm_idcard_reprint_list=s.perm_idcard_reprint_list,
                perm_reprint_request_list=s.perm_reprint_request_list,
                perm_confirmed_list=s.perm_confirmed_list,
                perm_idcard_add=s.perm_idcard_add,
                perm_idcard_edit=s.perm_idcard_edit,
                perm_idcard_delete=s.perm_idcard_delete,
                perm_idcard_info=s.perm_idcard_info,
                perm_idcard_approve=s.perm_idcard_approve,
                perm_idcard_verify=s.perm_idcard_verify,
                perm_idcard_updated_at=s.perm_idcard_updated_at,
                perm_idcard_delete_from_pool=s.perm_idcard_delete_from_pool,
                perm_idcard_clear_pending_path=getattr(s, 'perm_idcard_clear_pending_path', False),
                perm_reupload_idcard_image=s.perm_reupload_idcard_image,
                perm_idcard_retrieve=s.perm_idcard_retrieve,
                perm_idcard_bulk_upload=s.perm_idcard_bulk_upload,
                perm_idcard_bulk_download=s.perm_idcard_bulk_download,
                perm_idcard_download_image_rename_mode=s.perm_idcard_download_image_rename_mode,
                perm_idcard_download_image_generate_mode=s.perm_idcard_download_image_generate_mode,
                perm_idcard_bulk_reupload=s.perm_idcard_bulk_reupload,
                perm_idcard_upgrade_all=s.perm_idcard_upgrade_all,
                perm_mobile_app=s.perm_mobile_app,
                perm_manage_panel_backup=s.perm_manage_panel_backup,
                perm_manage_panel_email=s.perm_manage_panel_email,
                perm_pro_user_options=s.perm_pro_user_options,
                perm_pro_log_deletion_guard=s.perm_pro_log_deletion_guard,
                perm_pro_data_deletion_guard=s.perm_pro_data_deletion_guard,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            # Copy M2M assigned_clients using SQL
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT client_id FROM core_staff_assigned_clients WHERE staff_id = %s", [s.id])
                client_ids = [row[0] for row in cursor.fetchall()]
                for cid in client_ids:
                    cursor.execute("INSERT INTO operators_operator_assigned_clients (operator_id, client_id) VALUES (%s, %s)", [op.id, cid])

        elif s.staff_type == 'client_staff':
            # Create Assistant
            ast = Assistant.objects.using(db_alias).create(
                id=s.id,
                user=s.user,
                client_id=s.client_id,
                assigned_table_ids=s.assigned_table_ids,
                allowed_classes=s.allowed_classes,
                allowed_sections=s.allowed_sections,
                allowed_branches=s.allowed_branches,
                assignment_scopes=s.assignment_scopes,
                department=s.department,
                designation=s.designation,
                perm_idcard_client_list=s.perm_idcard_client_list,
                perm_manage_client_staff=s.perm_manage_client_staff,
                perm_idcard_setting_list=s.perm_idcard_setting_list,
                perm_idcard_setting_add=s.perm_idcard_setting_add,
                perm_idcard_setting_edit=s.perm_idcard_setting_edit,
                perm_idcard_setting_delete=s.perm_idcard_setting_delete,
                perm_idcard_setting_status=s.perm_idcard_setting_status,
                perm_idcard_pending_list=s.perm_idcard_pending_list,
                perm_idcard_verified_list=s.perm_idcard_verified_list,
                perm_idcard_pool_list=s.perm_idcard_pool_list,
                perm_idcard_approved_list=s.perm_idcard_approved_list,
                perm_idcard_download_list=s.perm_idcard_download_list,
                perm_idcard_reprint_list=s.perm_idcard_reprint_list,
                perm_reprint_request_list=s.perm_reprint_request_list,
                perm_confirmed_list=s.perm_confirmed_list,
                perm_idcard_add=s.perm_idcard_add,
                perm_idcard_edit=s.perm_idcard_edit,
                perm_idcard_delete=s.perm_idcard_delete,
                perm_idcard_info=s.perm_idcard_info,
                perm_idcard_approve=s.perm_idcard_approve,
                perm_idcard_verify=s.perm_idcard_verify,
                perm_idcard_updated_at=s.perm_idcard_updated_at,
                perm_idcard_delete_from_pool=s.perm_idcard_delete_from_pool,
                perm_idcard_clear_pending_path=getattr(s, 'perm_idcard_clear_pending_path', False),
                perm_reupload_idcard_image=s.perm_reupload_idcard_image,
                perm_idcard_retrieve=s.perm_idcard_retrieve,
                perm_idcard_bulk_upload=s.perm_idcard_bulk_upload,
                perm_idcard_bulk_download=s.perm_idcard_bulk_download,
                perm_idcard_download_image_rename_mode=s.perm_idcard_download_image_rename_mode,
                perm_idcard_download_image_generate_mode=s.perm_idcard_download_image_generate_mode,
                perm_idcard_bulk_reupload=s.perm_idcard_bulk_reupload,
                perm_idcard_upgrade_all=s.perm_idcard_upgrade_all,
                perm_mobile_app=s.perm_mobile_app,
                perm_manage_panel_backup=s.perm_manage_panel_backup,
                perm_manage_panel_email=s.perm_manage_panel_email,
                perm_pro_user_options=s.perm_pro_user_options,
                perm_pro_log_deletion_guard=s.perm_pro_log_deletion_guard,
                perm_pro_data_deletion_guard=s.perm_pro_data_deletion_guard,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            # Copy M2M assigned_groups using SQL
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT idcardgroup_id FROM core_staff_assigned_groups WHERE staff_id = %s", [s.id])
                group_ids = [row[0] for row in cursor.fetchall()]
                for gid in group_ids:
                    cursor.execute("INSERT INTO assistants_assistant_assigned_groups (assistant_id, idcardgroup_id) VALUES (%s, %s)", [ast.id, gid])

        elif s.staff_type == 'photographer':
            # Create Photographer
            Photographer.objects.using(db_alias).create(
                id=s.id,
                user=s.user,
                department=s.department,
                designation=s.designation,
                perm_idcard_pending_list=s.perm_idcard_pending_list,
                perm_idcard_verified_list=s.perm_idcard_verified_list,
                perm_idcard_add=s.perm_idcard_add,
                perm_idcard_info=s.perm_idcard_info,
                perm_mobile_app=s.perm_mobile_app,
                perm_idcard_bulk_download=s.perm_idcard_bulk_download,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0090_alter_user_role_photographer_and_more'),
        ('operators', '0001_initial'),
        ('assistants', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(migrate_staff_to_new_models),
    ]
