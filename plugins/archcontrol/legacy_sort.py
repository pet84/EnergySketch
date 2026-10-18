# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Ruby 2.2 equal-key ordering used by the original Windows exporter.

Independent Python expression of the qs6 partitioning algorithm described in
ruby/ruby v2_2_4 util.c (Tomoyuki Kawamura, 1995; Ruby contributors).
This is deliberately not a stable sort: CSV ties follow the source runtime.
No Ruby executable or native DLL is required. See NOTICE for attribution.
"""


def ruby_sort_by(values,key):
    items=[(key(value),value) for value in values]
    total=len(items)
    if total<2:
        return [v for _,v in items]

    def compare(i,j):
        a,b=items[i][0],items[j][0]
        return (a>b)-(a<b)

    def swap(i,j):
        items[i],items[j]=items[j],items[i]

    def rotate(a,b,c):
        items[a],items[b],items[c]=items[b],items[c],items[a]

    def median(a,b,c):
        if compare(a,b)<0:
            return b if compare(b,c)<0 else c if compare(a,c)<0 else a
        return b if compare(b,c)>0 else a if compare(a,c)<0 else c

    stack=[(0,total-1)]
    check_order=total>=63
    while stack:
        low,high=stack.pop()
        if high<=low:
            continue
        if high-low==1:
            if compare(low,high)>0:
                swap(low,high)
            continue
        left,right=low,high
        count=right-left+1
        pivot=left+count//2
        if count>=60:
            if count>=200:
                step=count//8
                a=median(left+step,left+2*step,left+3*step)
                b=median(pivot+step,pivot+2*step,pivot+3*step)
            else:
                step=count//4
                a,b=left+step,pivot+step
            pivot=median(a,pivot,b)
        first=compare(left,pivot)
        last=compare(pivot,right)
        mode='A'
        if first<0:
            if last<0:
                if check_order:
                    check_order=False
                    if all(compare(i,i+1)<=0 for i in range(left,right)):
                        continue
            elif last>0:
                if compare(left,right)<=0:
                    swap(pivot,right)
                else:
                    rotate(right,pivot,left)
            else:
                mode='B'
        elif first>0:
            if last>0:
                if check_order:
                    check_order=False
                    if all(compare(i,i+1)>=0 for i in range(left,right)):
                        items[left:right+1]=reversed(items[left:right+1])
                        continue
                swap(left,right)
            elif last<0:
                if compare(left,right)<=0:
                    swap(left,pivot)
                    mode='B'
                else:
                    rotate(left,pivot,right)
            else:
                swap(left,right)
        elif last>0:
            swap(left,right)
            mode='B'
        elif last==0:
            while True:
                left+=1
                if left==right:
                    break
                if left==pivot:
                    continue
                difference=compare(left,pivot)
                if difference>0:
                    swap(left,right)
                    left=low
                    break
                if difference<0:
                    swap(low,left)
                    left=low
                    mode='B'
                    break
            if left==right:
                continue
        equal_left=equal_right=True
        finished=False
        while not finished:
            if mode=='A':
                while True:
                    left+=1
                    if left==right:
                        left-=1
                        if left!=pivot:
                            swap(pivot,left)
                        left-=1
                        finished=True
                        break
                    if left==pivot:
                        continue
                    difference=compare(left,pivot)
                    if difference>0:
                        equal_right=False
                        break
                    if difference<0:
                        equal_left=False
                if finished:
                    break
                while True:
                    right-=1
                    if left==right:
                        left-=1
                        if left!=pivot:
                            swap(pivot,left)
                        left-=1
                        finished=True
                        break
                    if right==pivot:
                        pivot=left
                        break
                    difference=compare(right,pivot)
                    if difference<0:
                        equal_left=False
                        break
                    if difference==0:
                        break
            else:
                while True:
                    right-=1
                    if left==right:
                        right+=1
                        if right!=pivot:
                            swap(right,pivot)
                        right+=1
                        finished=True
                        break
                    if right==pivot:
                        continue
                    difference=compare(right,pivot)
                    if difference<0:
                        equal_left=False
                        break
                    if difference>0:
                        equal_right=False
                if finished:
                    break
                while True:
                    left+=1
                    if left==right:
                        right+=1
                        if right!=pivot:
                            swap(right,pivot)
                        right+=1
                        finished=True
                        break
                    if left==pivot:
                        pivot=right
                        break
                    difference=compare(left,pivot)
                    if difference>0:
                        equal_right=False
                        break
                    if difference==0:
                        break
            if not finished:
                swap(left,right)
        if not equal_left and not equal_right:
            # Process the smaller partition first, as the source runtime.
            if left-low<high-right:
                stack.extend([(right,high),(low,left)])
            else:
                stack.extend([(low,left),(right,high)])
        elif not equal_left:
            stack.append((low,left))
        elif not equal_right:
            stack.append((right,high))
    return [value for _,value in items]
