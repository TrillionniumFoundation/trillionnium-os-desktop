def parse_stacks(raw):
    roots={};tasks=set()
    for block in re.split(r'(?=^RootTask id=)',raw,flags=re.M):
        if not block.startswith('RootTask id='):continue
        head=block.splitlines()[0]
        rid=int(re.search(r'^RootTask id=(\d+)\b',head)[1])
        display=int(re.search(r'\bdisplayId=(\d+)\b',head)[1])
        user=int(re.search(r'\buserId=(\d+)\b',head)[1]);children=[]
        for line in block.splitlines():
            match=re.match(r'\s*taskId=(\d+):\s+(\S+)\s+.*?\buserId=(\d+)\b',line)
            require(not re.match(r'\s*taskId=',line) or match is not None,'UNPARSED_TASK_LINE')
            if match:
                tid=int(match[1]);require(tid not in tasks,'DUPLICATE_TASK');tasks.add(tid)
                children.append({'id':tid,'component':match[2],'user':int(match[3])})
        require(rid not in roots,'DUPLICATE_ROOT')
        roots[rid]={'display':display,'user':user,'freeform':'mWindowingMode=freeform' in block,'children':children}
    require(bool(roots) and bool(tasks),'UNRECOGNIZED_STACK_LIST')
    return roots,tasks

