def identity_projection(role,row,expected):
    need(type(row) is dict and set(row)==IDENTITY_KEYS,'FULL_PROCESS_IDENTITY_SCHEMA')
    need(row==expected,'FIXED_FULL_PROCESS_IDENTITY_DIFFERS')
    return {'role':role,'host_pid':row['host_pid'],'parent_host_pid':row['parent_host_pid'],
            'start_ticks':row['start_ticks'],'namespace_pids':row['namespace_pids'],
            'uids':row['uids'],'namespaces':row['namespaces'],
            'full_identity_sha256':sha(canonical(row)),
            'cmdline_json_bytes':len(canonical(row['cmdline'])),
            'cmdline_sha256':sha(canonical(row['cmdline'])),
            'executable_sha256':sha(canonical(row['executable'])),
            'cgroup_sha256':sha(canonical(row['cgroup'])),
            'complete_identity_equal_baseline':True}
